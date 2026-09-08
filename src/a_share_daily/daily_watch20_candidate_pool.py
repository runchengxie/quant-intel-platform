"""Fail-closed consumer validation for THS-hot sparse strict pools.

The producer owns snapshot assembly.  This module mirrors its published
contract so a delivery client cannot turn a sparse or tampered receipt into a
different universe.  In particular, missing ranks remain missing: selected
rows keep the rank observed in the protected source partition.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pandas as pd

from .daily_watch20_candidate_source import (
    THS_HOT_V2_BATCH_GAP_SECONDS,
    THS_HOT_V2_MAX_COMPONENT_SPAN_SECONDS,
    THS_HOT_V2_MAX_MISSING_RANKS,
    THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS,
    THS_HOT_V2_REQUIRED_TOP_RANKS,
    THS_HOT_V3_BATCH_GAP_SECONDS,
    THS_HOT_V3_MAX_COMPONENT_SPAN_SECONDS,
    THS_HOT_V3_MAX_MISSING_RANKS,
    THS_HOT_V3_MAX_SNAPSHOT_SYMBOLS,
    THS_HOT_V3_REQUIRED_TOP_RANKS,
    ReassembledTHSHotV2,
    THSHotV2SourceError,
    reassemble_latest_ths_hot_v2,
    reassemble_latest_ths_hot_v3,
)

THS_HOT_STRICT_V2 = "ths_hot_strict_v2"
THS_HOT_STRICT_V3 = "ths_hot_strict_v3"
THS_HOT_POLICY_SCHEMA_V2 = "daily_watch20.ths_hot_positive_close.v2"
THS_HOT_POLICY_SCHEMA_V3 = "daily_watch20.ths_hot_positive_close.v3"
THS_HOT_CLOSE_CUTOFF_MINUTE = 15 * 60
THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES = 60
THS_HOT_MIN_DELIVERY_SYMBOLS = 20
_ASSEMBLY_PATHS = frozenset({"v1_fast_path", "minute_sparse_unique", "batch_fallback"})
_HEX_DIGITS = frozenset("0123456789abcdef")


class THSHotV2ValidationError(ValueError):
    """Raised when sparse strict receipt evidence cannot support publication."""


THSHotV3ValidationError = THSHotV2ValidationError


def _mode_constants(mode: str) -> tuple[str, int, int, int, int, int]:
    if mode == THS_HOT_STRICT_V2:
        return (
            THS_HOT_POLICY_SCHEMA_V2,
            THS_HOT_V2_BATCH_GAP_SECONDS,
            THS_HOT_V2_MAX_COMPONENT_SPAN_SECONDS,
            THS_HOT_V2_MAX_MISSING_RANKS,
            THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS,
            THS_HOT_V2_REQUIRED_TOP_RANKS,
        )
    if mode == THS_HOT_STRICT_V3:
        return (
            THS_HOT_POLICY_SCHEMA_V3,
            THS_HOT_V3_BATCH_GAP_SECONDS,
            THS_HOT_V3_MAX_COMPONENT_SPAN_SECONDS,
            THS_HOT_V3_MAX_MISSING_RANKS,
            THS_HOT_V3_MAX_SNAPSHOT_SYMBOLS,
            THS_HOT_V3_REQUIRED_TOP_RANKS,
        )
    raise THSHotV2ValidationError(f"unsupported sparse strict candidate-pool mode: {mode}")


def _integer(candidate_pool: Mapping[str, Any], field: str, *, minimum: int = 0) -> int:
    raw = candidate_pool.get(field)
    if isinstance(raw, bool):
        raise THSHotV2ValidationError(f"receipt.candidate_pool.{field} is invalid")
    try:
        value = int(str(raw))
    except (TypeError, ValueError) as exc:
        raise THSHotV2ValidationError(f"receipt.candidate_pool.{field} is invalid") from exc
    if value < minimum:
        raise THSHotV2ValidationError(f"receipt.candidate_pool.{field} must be at least {minimum}")
    return value


def _boolean(candidate_pool: Mapping[str, Any], field: str) -> bool:
    value = candidate_pool.get(field)
    if type(value) is not bool:
        raise THSHotV2ValidationError(f"receipt.candidate_pool.{field} is invalid")
    return cast(bool, value)


def _timestamp(value: object, *, field: str, source_date: str) -> pd.Timestamp:
    parsed = pd.to_datetime(str(value or ""), errors="coerce")
    if pd.isna(parsed):
        raise THSHotV2ValidationError(f"receipt.candidate_pool.{field} is invalid")
    timestamp = parsed
    if timestamp.strftime("%Y%m%d") != source_date:
        raise THSHotV2ValidationError(f"receipt.candidate_pool.{field} date mismatch")
    return timestamp


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_files(candidate_pool: Mapping[str, Any], *, source_date: str) -> tuple[Path, ...]:
    root_text = str(candidate_pool.get("root") or "").strip()
    if not root_text:
        raise THSHotV2ValidationError("receipt.candidate_pool.root is required")
    root = Path(root_text).expanduser().resolve()
    partition = (root / "data" / f"trade_date={source_date}").resolve()
    entries = candidate_pool.get("files")
    if not isinstance(entries, list) or not entries:
        raise THSHotV2ValidationError("receipt.candidate_pool.files must be non-empty")
    paths: list[Path] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise THSHotV2ValidationError(f"receipt.candidate_pool.files[{index}] is invalid")
        path = Path(str(entry.get("path") or "")).expanduser().resolve()
        expected_hash = str(entry.get("sha256") or "").strip().lower()
        if path.suffix != ".parquet" or not path.is_relative_to(partition):
            raise THSHotV2ValidationError(
                "receipt.candidate_pool.files escapes the exact source partition"
            )
        if len(expected_hash) != 64 or not set(expected_hash).issubset(_HEX_DIGITS):
            raise THSHotV2ValidationError("receipt.candidate_pool.files contains an invalid sha256")
        if not path.is_file() or _sha256(path) != expected_hash:
            raise THSHotV2ValidationError(
                "receipt.candidate_pool.files is missing or hash-mismatched"
            )
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise THSHotV2ValidationError("receipt.candidate_pool.files contains duplicates")
    actual = tuple(sorted(path.resolve() for path in partition.rglob("*.parquet")))
    if tuple(sorted(paths)) != actual:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool.files does not match the source partition"
        )
    return tuple(paths)


def _validate_common_metadata(
    candidate_pool: Mapping[str, Any], *, source_date: str, mode: str
) -> dict[str, int]:
    expected = {
        "mode": mode,
        "source": "tushare.ths_hot",
        "restricted": True,
        "fail_closed": True,
        "positive_change_only": True,
    }
    if any(candidate_pool.get(field) != value for field, value in expected.items()):
        raise THSHotV2ValidationError(
            "receipt.candidate_pool sparse strict provenance or flags are invalid"
        )
    if str(candidate_pool.get("source_date") or "").replace("-", "") != source_date:
        raise THSHotV2ValidationError("receipt.candidate_pool.source_date mismatch")
    counts = {
        field: _integer(candidate_pool, field)
        for field in (
            "min_symbols",
            "snapshot_min_symbols",
            "snapshot_unique_symbols",
            "snapshot_rows",
            "pool_symbols",
            "eligible_intersection_symbols",
        )
    }
    *_, max_snapshot_symbols, _required_top_ranks = _mode_constants(mode)
    if counts["min_symbols"] < THS_HOT_MIN_DELIVERY_SYMBOLS:
        raise THSHotV2ValidationError("receipt.candidate_pool.min_symbols is too small")
    if not (
        counts["min_symbols"]
        <= counts["snapshot_min_symbols"]
        <= counts["snapshot_unique_symbols"]
        <= max_snapshot_symbols
    ):
        raise THSHotV2ValidationError("receipt.candidate_pool snapshot symbol evidence is invalid")
    if counts["snapshot_rows"] < counts["snapshot_unique_symbols"]:
        raise THSHotV2ValidationError("receipt.candidate_pool.snapshot_rows is too small")
    if counts["pool_symbols"] < counts["min_symbols"]:
        raise THSHotV2ValidationError("receipt.candidate_pool.pool_symbols is too small")
    if counts["eligible_intersection_symbols"] < THS_HOT_MIN_DELIVERY_SYMBOLS:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool.eligible_intersection_symbols must be at least 20"
        )
    return counts


def _validate_policy_id(
    candidate_pool: Mapping[str, Any], counts: Mapping[str, int], *, mode: str
) -> None:
    (
        schema,
        batch_gap_seconds,
        max_component_span_seconds,
        max_missing_ranks,
        max_snapshot_symbols,
        required_top_ranks,
    ) = _mode_constants(mode)
    constants = (
        _integer(candidate_pool, "close_cutoff_minute"),
        _integer(candidate_pool, "max_snapshot_fallback_minutes"),
        _integer(candidate_pool, "batch_gap_seconds"),
        _integer(candidate_pool, "max_component_span_seconds"),
        _integer(candidate_pool, "max_missing_ranks"),
        _integer(candidate_pool, "max_snapshot_symbols"),
        _boolean(candidate_pool, "require_rank_one"),
        _integer(candidate_pool, "required_top_ranks"),
    )
    expected_constants = (
        THS_HOT_CLOSE_CUTOFF_MINUTE,
        THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES,
        batch_gap_seconds,
        max_component_span_seconds,
        max_missing_ranks,
        max_snapshot_symbols,
        True,
        required_top_ranks,
    )
    if constants != expected_constants:
        raise THSHotV2ValidationError("receipt.candidate_pool sparse strict constants are invalid")
    expected_policy_id = (
        f"{schema}:min_symbols={counts['min_symbols']}:"
        f"snapshot_min_symbols={counts['snapshot_min_symbols']}:"
        f"close_cutoff_minute={THS_HOT_CLOSE_CUTOFF_MINUTE}:"
        f"max_snapshot_fallback_minutes={THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES}:"
        f"batch_gap_seconds={batch_gap_seconds}:"
        f"max_component_span_seconds={max_component_span_seconds}:"
        f"max_missing_ranks={max_missing_ranks}:"
        f"max_snapshot_symbols={max_snapshot_symbols}:"
        "require_rank_one=true:"
        f"required_top_ranks={required_top_ranks}"
    )
    if candidate_pool.get("policy_id") != expected_policy_id:
        raise THSHotV2ValidationError("receipt.candidate_pool.policy_id is invalid")


def _missing_rank_evidence(
    candidate_pool: Mapping[str, Any], *, snapshot_unique: int, mode: str
) -> tuple[int, ...]:
    *_, max_missing_ranks, max_snapshot_symbols, required_top_ranks = _mode_constants(mode)
    if _integer(candidate_pool, "rank_ties") != 0:
        raise THSHotV2ValidationError("receipt.candidate_pool.rank_ties must be zero")
    if _integer(candidate_pool, "deduplicated_snapshot_rows") != snapshot_unique:
        raise THSHotV2ValidationError("receipt.candidate_pool.deduplicated_snapshot_rows mismatch")
    raw_missing = candidate_pool.get("missing_ranks")
    if not isinstance(raw_missing, list) or any(
        type(rank) is not int or rank <= 0 for rank in raw_missing
    ):
        raise THSHotV2ValidationError("receipt.candidate_pool.missing_ranks is invalid")
    missing = tuple(cast(list[int], raw_missing))
    if missing != tuple(sorted(set(missing))):
        raise THSHotV2ValidationError(
            "receipt.candidate_pool.missing_ranks must be sorted and unique"
        )
    if len(missing) > max_missing_ranks:
        raise THSHotV2ValidationError("receipt.candidate_pool has too many missing ranks")
    if any(rank <= required_top_ranks for rank in missing):
        raise THSHotV2ValidationError("receipt.candidate_pool is missing a required top rank")
    inferred_max_rank = snapshot_unique + len(missing)
    if inferred_max_rank > max_snapshot_symbols or any(
        rank > inferred_max_rank for rank in missing
    ):
        raise THSHotV2ValidationError(
            "receipt.candidate_pool.missing_ranks contradict snapshot rank evidence"
        )
    status = candidate_pool.get("rank_coverage_status")
    expected_status = "complete" if not missing else "degraded"
    if status != expected_status:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool.rank_coverage_status contradicts missing_ranks"
        )
    return missing


def _validate_row_conservation(
    candidate_pool: Mapping[str, Any], *, counts: Mapping[str, int]
) -> None:
    duplicate_rows = _integer(candidate_pool, "duplicate_symbol_rows_removed")
    out_of_scope_rows = _integer(candidate_pool, "out_of_scope_rows_removed")
    expected_snapshot_rows = counts["snapshot_unique_symbols"] + duplicate_rows + out_of_scope_rows
    if counts["snapshot_rows"] != expected_snapshot_rows:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool snapshot row evidence is not conserved"
        )
    if _integer(candidate_pool, "raw_rows") < counts["snapshot_rows"]:
        raise THSHotV2ValidationError("receipt.candidate_pool raw row evidence is not conserved")
    non_positive = _integer(candidate_pool, "non_positive_rows_removed")
    if counts["pool_symbols"] != counts["snapshot_unique_symbols"] - non_positive:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool positive-pool evidence is not conserved"
        )
    assembly_path = candidate_pool.get("assembly_path")
    if assembly_path not in _ASSEMBLY_PATHS:
        raise THSHotV2ValidationError("receipt.candidate_pool.assembly_path is invalid")
    if assembly_path == "v1_fast_path" and duplicate_rows:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool v1_fast_path cannot remove duplicate rows"
        )
    if assembly_path == "batch_fallback" and duplicate_rows:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool batch_fallback cannot remove duplicate rows"
        )


def _component_range(
    candidate_pool: Mapping[str, Any], *, source_date: str, mode: str
) -> tuple[pd.Timestamp, pd.Timestamp]:
    _, _, max_component_span_seconds, _, _, _ = _mode_constants(mode)
    start = _timestamp(
        candidate_pool.get("component_time_start"),
        field="component_time_start",
        source_date=source_date,
    )
    end = _timestamp(
        candidate_pool.get("component_time_end"),
        field="component_time_end",
        source_date=source_date,
    )
    span = int((end - start).total_seconds())
    if end < start or _integer(candidate_pool, "component_span_seconds") != span:
        raise THSHotV2ValidationError("receipt.candidate_pool component time range is invalid")
    if span > max_component_span_seconds:
        raise THSHotV2ValidationError("receipt.candidate_pool component span is invalid")
    snapshot_minute = _timestamp(
        candidate_pool.get("snapshot_minute"),
        field="snapshot_minute",
        source_date=source_date,
    )
    if snapshot_minute != end.floor("min"):
        raise THSHotV2ValidationError(
            "receipt.candidate_pool.snapshot_minute does not match component end"
        )
    if candidate_pool.get("snapshot_time_min") != candidate_pool.get("component_time_start"):
        raise THSHotV2ValidationError("receipt.candidate_pool.snapshot_time_min mismatch")
    if candidate_pool.get("snapshot_time_max") != candidate_pool.get("component_time_end"):
        raise THSHotV2ValidationError("receipt.candidate_pool.snapshot_time_max mismatch")
    if candidate_pool.get("assembly_path") in {
        "v1_fast_path",
        "minute_sparse_unique",
    } and start.floor("min") != end.floor("min"):
        raise THSHotV2ValidationError(
            "receipt.candidate_pool minute assembly spans multiple minutes"
        )
    return start, end


def _read_source_rows(paths: tuple[Path, ...]) -> pd.DataFrame:
    try:
        return pd.concat(
            (pd.read_parquet(path) for path in paths),
            ignore_index=True,
            sort=False,
        )
    except (OSError, ValueError) as exc:
        raise THSHotV2ValidationError("cannot read sparse strict candidate source files") from exc


def _validate_reassembled_evidence(
    snapshot: ReassembledTHSHotV2,
    candidate_pool: Mapping[str, Any],
    *,
    missing_ranks: tuple[int, ...],
    counts: Mapping[str, int],
) -> None:
    numeric_evidence = {
        "raw_rows": snapshot.raw_rows,
        "snapshot_rows": snapshot.snapshot_rows,
        "snapshot_unique_symbols": snapshot.snapshot_unique_symbols,
        "skipped_incomplete_snapshots": snapshot.skipped_incomplete_snapshots,
        "duplicate_symbol_rows_removed": snapshot.duplicate_symbol_rows_removed,
        "out_of_scope_rows_removed": snapshot.out_of_scope_rows_removed,
        "rank_ties": snapshot.rank_ties,
        "component_span_seconds": snapshot.component_span_seconds,
    }
    for field, expected in numeric_evidence.items():
        if _integer(candidate_pool, field) != expected:
            raise THSHotV2ValidationError(
                f"receipt.candidate_pool.{field} does not match the latest source snapshot"
            )
    string_evidence = {
        "assembly_path": snapshot.assembly_path,
        "snapshot_minute": snapshot.snapshot_minute,
        "latest_observed_minute": snapshot.latest_observed_minute,
        "snapshot_time_min": snapshot.snapshot_time_min,
        "snapshot_time_max": snapshot.snapshot_time_max,
        "component_time_start": snapshot.component_time_start,
        "component_time_end": snapshot.component_time_end,
    }
    for field, expected in string_evidence.items():
        if candidate_pool.get(field) != expected:
            raise THSHotV2ValidationError(
                f"receipt.candidate_pool.{field} does not match the latest source snapshot"
            )
    if snapshot.missing_ranks != missing_ranks:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool.missing_ranks mismatch the latest source snapshot"
        )
    if counts["snapshot_rows"] != snapshot.snapshot_rows or counts[
        "snapshot_unique_symbols"
    ] != len(snapshot.frame):
        raise THSHotV2ValidationError(
            "receipt.candidate_pool counts mismatch the latest source snapshot"
        )


def _validate_selected_source_rows(
    snapshot: ReassembledTHSHotV2,
    candidate_pool: Mapping[str, Any],
    frame: pd.DataFrame,
    *,
    counts: Mapping[str, int],
) -> None:
    pct = cast(pd.Series, pd.to_numeric(snapshot.frame["pct_change"], errors="coerce"))
    finite = pct.map(lambda value: math.isfinite(float(value)) if pd.notna(value) else False)
    positive = cast(pd.Series, pct.gt(0) & finite)
    if int(positive.sum()) != counts["pool_symbols"]:
        raise THSHotV2ValidationError("receipt.candidate_pool.pool_symbols mismatch source")
    if _integer(candidate_pool, "non_positive_rows_removed") != int((~positive).sum()):
        raise THSHotV2ValidationError(
            "receipt.candidate_pool.non_positive_rows_removed mismatch source"
        )
    source_by_symbol = snapshot.frame.set_index("_source_symbol", drop=False)
    selected_rows = cast(list[dict[str, Any]], frame.to_dict(orient="records"))
    for row in selected_rows:
        symbol = str(row["symbol"])
        if symbol not in source_by_symbol.index:
            raise THSHotV2ValidationError("watchlist contains a symbol outside source snapshot")
        source_row = source_by_symbol.loc[symbol]
        if isinstance(source_row, pd.DataFrame):
            raise THSHotV2ValidationError("sparse strict source contains duplicate symbols")
        source_rank = int(source_row["_source_rank"])
        source_change = float(source_row["pct_change"])
        source_time = cast(pd.Timestamp, source_row["_source_time"])
        selected_time = cast(pd.Timestamp, row["ths_hot_rank_time"])
        if (
            int(row["ths_hot_rank"]) != source_rank
            or not math.isclose(
                float(row["ths_hot_pct_change"]),
                source_change,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or selected_time.strftime("%Y-%m-%d %H:%M:%S")
            != source_time.strftime("%Y-%m-%d %H:%M:%S")
        ):
            raise THSHotV2ValidationError(
                "watchlist THS-hot fields do not preserve source rank evidence"
            )


def _validate_ths_hot_sparse(
    receipt: Mapping[str, Any], frame: pd.DataFrame, *, source_date: str, mode: str
) -> None:
    """Validate sparse strict receipt, protected input, and selected-row evidence."""

    candidate_pool = receipt.get("candidate_pool")
    if not isinstance(candidate_pool, Mapping):
        raise THSHotV2ValidationError("receipt.candidate_pool is required")
    counts = _validate_common_metadata(candidate_pool, source_date=source_date, mode=mode)
    _validate_policy_id(candidate_pool, counts, mode=mode)
    missing_ranks = _missing_rank_evidence(
        candidate_pool,
        snapshot_unique=counts["snapshot_unique_symbols"],
        mode=mode,
    )
    if candidate_pool.get("assembly_path") == "v1_fast_path" and missing_ranks:
        raise THSHotV2ValidationError(
            "receipt.candidate_pool v1_fast_path cannot contain missing ranks"
        )
    _validate_row_conservation(candidate_pool, counts=counts)
    start, end = _component_range(candidate_pool, source_date=source_date, mode=mode)
    *_, max_snapshot_symbols, _required_top_ranks = _mode_constants(mode)
    ranks = cast(pd.Series, frame["ths_hot_rank"])
    if bool(ranks.duplicated().any()) or bool(ranks.gt(max_snapshot_symbols).any()):
        raise THSHotV2ValidationError(
            "watchlist sparse strict ranks must be unique and at most 100"
        )
    inferred_max_rank = counts["snapshot_unique_symbols"] + len(missing_ranks)
    if bool(ranks.gt(inferred_max_rank).any()) or bool(ranks.isin(missing_ranks).any()):
        raise THSHotV2ValidationError("watchlist ranks contradict missing-rank evidence")
    rank_times = cast(pd.Series, frame["ths_hot_rank_time"])
    if bool(rank_times.lt(start).any() or rank_times.gt(end).any()):
        raise THSHotV2ValidationError("watchlist rank_time escapes source component")
    paths = _manifest_files(candidate_pool, source_date=source_date)
    raw = _read_source_rows(paths)
    try:
        reassemble = (
            reassemble_latest_ths_hot_v3
            if mode == THS_HOT_STRICT_V3
            else reassemble_latest_ths_hot_v2
        )
        snapshot = reassemble(
            raw,
            source_date=source_date,
            snapshot_min_symbols=counts["snapshot_min_symbols"],
            close_cutoff_minute=THS_HOT_CLOSE_CUTOFF_MINUTE,
            max_snapshot_fallback_minutes=THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES,
        )
    except THSHotV2SourceError as exc:
        raise THSHotV2ValidationError(str(exc)) from exc
    _validate_reassembled_evidence(
        snapshot,
        candidate_pool,
        missing_ranks=missing_ranks,
        counts=counts,
    )
    _validate_selected_source_rows(snapshot, candidate_pool, frame, counts=counts)


def validate_ths_hot_strict_v2(
    receipt: Mapping[str, Any], frame: pd.DataFrame, *, source_date: str
) -> None:
    """Validate a historical strict-v2 artifact."""

    _validate_ths_hot_sparse(
        receipt,
        frame,
        source_date=source_date,
        mode=THS_HOT_STRICT_V2,
    )


def validate_ths_hot_strict_v3(
    receipt: Mapping[str, Any], frame: pd.DataFrame, *, source_date: str
) -> None:
    """Validate a production strict-v3 artifact."""

    _validate_ths_hot_sparse(
        receipt,
        frame,
        source_date=source_date,
        mode=THS_HOT_STRICT_V3,
    )


__all__ = [
    "THS_HOT_STRICT_V2",
    "THS_HOT_STRICT_V3",
    "THS_HOT_V2_MAX_MISSING_RANKS",
    "THSHotV2ValidationError",
    "THSHotV3ValidationError",
    "validate_ths_hot_strict_v2",
    "validate_ths_hot_strict_v3",
]
