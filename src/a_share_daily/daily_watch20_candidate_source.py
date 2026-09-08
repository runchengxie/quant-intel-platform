"""Reassemble canonical THS-hot sparse snapshots from protected rows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import pandas as pd

THS_HOT_V2_BATCH_GAP_SECONDS = 15
THS_HOT_V2_MAX_COMPONENT_SPAN_SECONDS = 180
THS_HOT_V2_MAX_MISSING_RANKS = 2
THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS = 100
THS_HOT_V2_REQUIRED_TOP_RANKS = 20
THS_HOT_V3_BATCH_GAP_SECONDS = THS_HOT_V2_BATCH_GAP_SECONDS
THS_HOT_V3_MAX_COMPONENT_SPAN_SECONDS = THS_HOT_V2_MAX_COMPONENT_SPAN_SECONDS
THS_HOT_V3_MAX_MISSING_RANKS = THS_HOT_V2_MAX_MISSING_RANKS
THS_HOT_V3_MAX_SNAPSHOT_SYMBOLS = THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS
THS_HOT_V3_REQUIRED_TOP_RANKS = 1


class THSHotV2SourceError(ValueError):
    """Raised when protected rows cannot produce a canonical v2 snapshot."""


class _NoCompleteMinute(THSHotV2SourceError):
    """Raised when minute assembly must use the batch fallback."""


@dataclass(frozen=True)
class ReassembledTHSHotV2:
    frame: pd.DataFrame
    assembly_path: str
    raw_rows: int
    snapshot_rows: int
    snapshot_unique_symbols: int
    snapshot_minute: str
    latest_observed_minute: str
    skipped_incomplete_snapshots: int
    snapshot_time_min: str
    snapshot_time_max: str
    duplicate_symbol_rows_removed: int
    out_of_scope_rows_removed: int
    missing_ranks: tuple[int, ...]
    rank_ties: int
    component_time_start: str
    component_time_end: str
    component_span_seconds: int


@dataclass(frozen=True)
class _AssemblyEvidence:
    assembly_path: str
    raw_rows: int
    snapshot_rows: int
    snapshot_minute: pd.Timestamp
    latest_observed_minute: pd.Timestamp
    skipped_incomplete_snapshots: int
    component_times: tuple[str, str, int]
    duplicate_rows: int
    out_of_scope_rows: int
    missing_ranks: tuple[int, ...]


def prepare_ths_hot_source(raw: pd.DataFrame, *, source_date: str) -> pd.DataFrame:
    """Validate immutable partition-wide fields and add assembly columns."""

    required = {"trade_date", "data_type", "platform_market", "rank", "pct_change", "rank_time"}
    missing = sorted(required - set(raw.columns))
    symbol_column = (
        "symbol" if "symbol" in raw.columns else "ts_code" if "ts_code" in raw.columns else None
    )
    if symbol_column is None:
        missing.append("symbol|ts_code")
    if missing or raw.empty:
        raise THSHotV2SourceError(
            f"sparse strict candidate source is missing columns or rows: {missing}"
        )
    dates = cast(pd.Series, raw["trade_date"]).astype(str).str.replace("-", "", regex=False)
    if set(dates) != {source_date}:
        raise THSHotV2SourceError("sparse strict candidate source contains another date")
    if set(cast(pd.Series, raw["data_type"]).astype(str)) != {"热股"}:
        raise THSHotV2SourceError("sparse strict candidate source data_type is invalid")
    if set(cast(pd.Series, raw["platform_market"]).astype(str)) != {"a_share"}:
        raise THSHotV2SourceError("sparse strict candidate source market is invalid")
    work = raw.copy()
    assert symbol_column is not None
    work["_source_symbol"] = (
        cast(pd.Series, work[symbol_column]).astype("string").str.strip().str.upper()
    )
    work["_source_time"] = pd.to_datetime(work["rank_time"], errors="coerce")
    rank_times = cast(pd.Series, work["_source_time"])
    if bool(rank_times.isna().any()) or set(rank_times.dt.strftime("%Y%m%d")) != {source_date}:
        raise THSHotV2SourceError("sparse strict candidate source rank_time is invalid")
    work["_source_row"] = range(len(work))
    work["_snapshot_minute"] = rank_times.dt.floor("min")
    work["_in_scope"] = cast(pd.Series, work["_source_symbol"]).str.fullmatch(
        r"\d{6}\.(?:SH|SZ)", na=False
    )
    return work


def _component_times(frame: pd.DataFrame) -> tuple[str, str, int]:
    start = cast(pd.Timestamp, frame["_source_time"].min())
    end = cast(pd.Timestamp, frame["_source_time"].max())
    return (
        start.strftime("%Y-%m-%d %H:%M:%S"),
        end.strftime("%Y-%m-%d %H:%M:%S"),
        int((end - start).total_seconds()),
    )


def _rank_evidence(
    frame: pd.DataFrame,
    *,
    required_top_ranks: int,
    policy_version: str,
) -> tuple[int, ...]:
    rank_column = "_source_rank" if "_source_rank" in frame.columns else "rank"
    ranks = cast(pd.Series, pd.to_numeric(frame[rank_column], errors="coerce"))
    if (
        frame.empty
        or bool(ranks.isna().any())
        or bool(ranks.le(0).any())
        or bool(ranks.gt(THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS).any())
        or bool(ranks.mod(1).ne(0).any())
    ):
        raise THSHotV2SourceError("sparse strict source snapshot contains invalid ranks")
    integer_ranks = set(ranks.astype(int))
    if len(integer_ranks) != len(frame):
        raise THSHotV2SourceError("sparse strict source snapshot contains rank ties")
    required = set(range(1, required_top_ranks + 1))
    if missing_required := sorted(required - integer_ranks):
        raise THSHotV2SourceError(
            f"strict-{policy_version} source snapshot is missing required top ranks: "
            f"{missing_required}"
        )
    missing = tuple(sorted(set(range(1, max(integer_ranks) + 1)) - integer_ranks))
    if len(missing) > THS_HOT_V2_MAX_MISSING_RANKS:
        raise THSHotV2SourceError("sparse strict source snapshot has too many missing ranks")
    return missing


def _minute_counts(work: pd.DataFrame) -> pd.Series:
    in_scope = cast(pd.Series, work["_in_scope"]).fillna(False).astype(bool)
    return cast(
        pd.Series,
        work.loc[in_scope].groupby("_snapshot_minute", sort=True)["_source_symbol"].nunique(),
    )


def _validate_close_and_age(
    selected_time: pd.Timestamp,
    latest_observed: pd.Timestamp,
    *,
    close_cutoff_minute: int,
    max_snapshot_fallback_minutes: int,
) -> None:
    minute_of_day = selected_time.hour * 60 + selected_time.minute
    if minute_of_day < close_cutoff_minute:
        raise THSHotV2SourceError("sparse strict source has no qualifying close snapshot")
    fallback_minutes = int((latest_observed - selected_time).total_seconds() // 60)
    if fallback_minutes > max_snapshot_fallback_minutes:
        raise THSHotV2SourceError("sparse strict source snapshot is too far behind the latest row")


def _assemble_sparse(
    selected: pd.DataFrame,
    *,
    snapshot_min_symbols: int,
    require_raw_unique_symbols: bool,
    required_top_ranks: int,
    policy_version: str,
) -> tuple[pd.DataFrame, int, int, tuple[int, ...]]:
    in_scope = cast(pd.Series, selected["_in_scope"]).fillna(False).astype(bool)
    out_of_scope_rows = int((~in_scope).sum())
    work = cast(pd.DataFrame, selected.loc[in_scope]).copy()
    if work.empty:
        raise THSHotV2SourceError("sparse strict source snapshot has no in-scope symbols")
    ranks = cast(pd.Series, pd.to_numeric(work["rank"], errors="coerce"))
    if (
        bool(ranks.isna().any())
        or bool(ranks.le(0).any())
        or bool(ranks.gt(THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS).any())
        or bool(ranks.mod(1).ne(0).any())
    ):
        raise THSHotV2SourceError("sparse strict source snapshot contains invalid ranks")
    work["_source_rank"] = ranks.astype(int)
    work["_source_pct"] = pd.to_numeric(work["pct_change"], errors="coerce")
    for _, same_observation in work.groupby(
        ["_source_symbol", "_source_time"], sort=False, dropna=False
    ):
        if (
            same_observation["_source_rank"].nunique(dropna=False) > 1
            or same_observation["_source_pct"].nunique(dropna=False) > 1
        ):
            raise THSHotV2SourceError("sparse strict source has conflicting same-time rows")
    duplicate_rows = len(work) - int(work["_source_symbol"].nunique())
    if require_raw_unique_symbols and duplicate_rows:
        raise THSHotV2SourceError("sparse strict batch fallback contains repeated symbols")
    deduplicated = (
        work.sort_values(["_source_symbol", "_source_time", "_source_row"], kind="mergesort")
        .drop_duplicates("_source_symbol", keep="last")
        .copy()
    )
    if len(deduplicated) < snapshot_min_symbols:
        raise THSHotV2SourceError("sparse strict source snapshot is incomplete after deduplication")
    missing_ranks = _rank_evidence(
        deduplicated,
        required_top_ranks=required_top_ranks,
        policy_version=policy_version,
    )
    return deduplicated, duplicate_rows, out_of_scope_rows, missing_ranks


def _build_result(
    snapshot: pd.DataFrame,
    evidence: _AssemblyEvidence,
) -> ReassembledTHSHotV2:
    start, end, span = evidence.component_times
    return ReassembledTHSHotV2(
        frame=snapshot,
        assembly_path=evidence.assembly_path,
        raw_rows=evidence.raw_rows,
        snapshot_rows=evidence.snapshot_rows,
        snapshot_unique_symbols=len(snapshot),
        snapshot_minute=evidence.snapshot_minute.strftime("%Y-%m-%d %H:%M"),
        latest_observed_minute=evidence.latest_observed_minute.strftime("%Y-%m-%d %H:%M"),
        skipped_incomplete_snapshots=evidence.skipped_incomplete_snapshots,
        snapshot_time_min=start,
        snapshot_time_max=end,
        duplicate_symbol_rows_removed=evidence.duplicate_rows,
        out_of_scope_rows_removed=evidence.out_of_scope_rows,
        missing_ranks=evidence.missing_ranks,
        rank_ties=0,
        component_time_start=start,
        component_time_end=end,
        component_span_seconds=span,
    )


def _select_v1_fast_path(
    work: pd.DataFrame,
    *,
    snapshot_min_symbols: int,
    close_cutoff_minute: int,
    max_snapshot_fallback_minutes: int,
    required_top_ranks: int,
    policy_version: str,
) -> ReassembledTHSHotV2:
    counts = _minute_counts(work)
    complete = counts.loc[counts.ge(snapshot_min_symbols)].index
    if len(complete) == 0:
        raise _NoCompleteMinute("sparse strict source has no complete minute")
    latest_minute = cast(pd.Timestamp, complete.max())
    latest_observed = cast(pd.Timestamp, work["_snapshot_minute"].max())
    _validate_close_and_age(
        latest_minute,
        latest_observed,
        close_cutoff_minute=close_cutoff_minute,
        max_snapshot_fallback_minutes=max_snapshot_fallback_minutes,
    )
    selected = cast(pd.DataFrame, work.loc[work["_snapshot_minute"].eq(latest_minute)]).copy()
    ranks = cast(pd.Series, pd.to_numeric(selected["rank"], errors="coerce"))
    if (
        bool(ranks.isna().any())
        or not bool(ranks.map(math.isfinite).all())
        or bool(ranks.le(0).any())
        or bool(ranks.mod(1).ne(0).any())
    ):
        raise THSHotV2SourceError("sparse strict source does not satisfy the v1 fast path")
    rank_values = set(ranks.astype(int))
    if len(rank_values) != len(selected) or rank_values != set(range(1, len(selected) + 1)):
        raise THSHotV2SourceError("sparse strict source does not satisfy the v1 fast path")
    selected["_source_rank"] = ranks.astype(int)
    in_scope = cast(pd.Series, selected["_in_scope"]).fillna(False).astype(bool)
    out_of_scope_rows = int((~in_scope).sum())
    snapshot = cast(pd.DataFrame, selected.loc[in_scope]).copy()
    if bool(cast(pd.Series, snapshot["_source_symbol"]).duplicated().any()):
        raise THSHotV2SourceError("sparse strict v1 fast path contains duplicate symbols")
    if len(snapshot) < snapshot_min_symbols:
        raise THSHotV2SourceError("sparse strict v1 fast path is incomplete after scope filtering")
    missing_ranks = _rank_evidence(
        snapshot,
        required_top_ranks=required_top_ranks,
        policy_version=policy_version,
    )
    return _build_result(
        snapshot,
        _AssemblyEvidence(
            assembly_path="v1_fast_path",
            raw_rows=len(work),
            snapshot_rows=len(selected),
            snapshot_minute=latest_minute,
            latest_observed_minute=latest_observed,
            skipped_incomplete_snapshots=int((counts.index > latest_minute).sum()),
            component_times=_component_times(selected),
            duplicate_rows=0,
            out_of_scope_rows=out_of_scope_rows,
            missing_ranks=missing_ranks,
        ),
    )


def _select_sparse_minute(
    work: pd.DataFrame,
    *,
    snapshot_min_symbols: int,
    close_cutoff_minute: int,
    max_snapshot_fallback_minutes: int,
    required_top_ranks: int,
    policy_version: str,
) -> ReassembledTHSHotV2:
    counts = _minute_counts(work)
    complete = counts.loc[counts.ge(snapshot_min_symbols)].index
    if len(complete) == 0:
        raise _NoCompleteMinute("sparse strict source has no complete minute")
    latest_minute = cast(pd.Timestamp, complete.max())
    latest_observed = cast(pd.Timestamp, work["_snapshot_minute"].max())
    _validate_close_and_age(
        latest_minute,
        latest_observed,
        close_cutoff_minute=close_cutoff_minute,
        max_snapshot_fallback_minutes=max_snapshot_fallback_minutes,
    )
    selected = cast(pd.DataFrame, work.loc[work["_snapshot_minute"].eq(latest_minute)]).copy()
    snapshot, duplicates, out_of_scope, missing = _assemble_sparse(
        selected,
        snapshot_min_symbols=snapshot_min_symbols,
        require_raw_unique_symbols=False,
        required_top_ranks=required_top_ranks,
        policy_version=policy_version,
    )
    return _build_result(
        snapshot,
        _AssemblyEvidence(
            assembly_path="minute_sparse_unique",
            raw_rows=len(work),
            snapshot_rows=len(selected),
            snapshot_minute=latest_minute,
            latest_observed_minute=latest_observed,
            skipped_incomplete_snapshots=int((counts.index > latest_minute).sum()),
            component_times=_component_times(selected),
            duplicate_rows=duplicates,
            out_of_scope_rows=out_of_scope,
            missing_ranks=missing,
        ),
    )


def _select_batch_fallback(
    work: pd.DataFrame,
    *,
    snapshot_min_symbols: int,
    close_cutoff_minute: int,
    max_snapshot_fallback_minutes: int,
    required_top_ranks: int,
    policy_version: str,
) -> ReassembledTHSHotV2:
    in_scope = cast(pd.Series, work["_in_scope"]).fillna(False).astype(bool)
    observations = cast(pd.DataFrame, work.loc[in_scope]).sort_values(
        ["_source_time", "_source_row"], kind="mergesort"
    )
    if observations.empty:
        raise THSHotV2SourceError("sparse strict source has no in-scope batch rows")
    observations = observations.copy()
    gaps = cast(pd.Series, observations["_source_time"]).diff().dt.total_seconds()
    observations["_component"] = gaps.gt(THS_HOT_V2_BATCH_GAP_SECONDS).cumsum()
    components = [
        (index, component.copy(), int(component["_source_symbol"].nunique()))
        for index, (_, component) in enumerate(observations.groupby("_component", sort=True))
    ]
    complete = [item for item in components if item[2] >= snapshot_min_symbols]
    if not complete:
        raise THSHotV2SourceError("sparse strict source has no complete batch fallback")
    _, selected, _ = max(
        complete,
        key=lambda item: (cast(pd.Timestamp, item[1]["_source_time"].max()), item[0]),
    )
    component_times = _component_times(selected)
    selected_end = cast(pd.Timestamp, pd.Timestamp(component_times[1]))
    latest_observed = cast(pd.Timestamp, work["_source_time"].max())
    _validate_close_and_age(
        selected_end,
        latest_observed,
        close_cutoff_minute=close_cutoff_minute,
        max_snapshot_fallback_minutes=max_snapshot_fallback_minutes,
    )
    if component_times[2] > THS_HOT_V2_MAX_COMPONENT_SPAN_SECONDS:
        raise THSHotV2SourceError("sparse strict batch fallback exceeds the component span")
    snapshot, duplicates, out_of_scope, missing = _assemble_sparse(
        selected,
        snapshot_min_symbols=snapshot_min_symbols,
        require_raw_unique_symbols=True,
        required_top_ranks=required_top_ranks,
        policy_version=policy_version,
    )
    later_incomplete = sum(
        cast(pd.Timestamp, component["_source_time"].max()) > selected_end
        for _, component, unique_symbols in components
        if unique_symbols < snapshot_min_symbols
    )
    return _build_result(
        snapshot,
        _AssemblyEvidence(
            assembly_path="batch_fallback",
            raw_rows=len(work),
            snapshot_rows=len(selected),
            snapshot_minute=selected_end.floor("min"),
            latest_observed_minute=latest_observed.floor("min"),
            skipped_incomplete_snapshots=later_incomplete,
            component_times=component_times,
            duplicate_rows=duplicates,
            out_of_scope_rows=out_of_scope,
            missing_ranks=missing,
        ),
    )


def _reassemble_latest_ths_hot_sparse(
    raw: pd.DataFrame,
    *,
    source_date: str,
    snapshot_min_symbols: int,
    close_cutoff_minute: int,
    max_snapshot_fallback_minutes: int,
    required_top_ranks: int,
    policy_version: str,
) -> ReassembledTHSHotV2:
    """Mirror producer precedence and return the latest qualifying snapshot."""

    work = prepare_ths_hot_source(raw, source_date=source_date)
    try:
        return _select_v1_fast_path(
            work,
            snapshot_min_symbols=snapshot_min_symbols,
            close_cutoff_minute=close_cutoff_minute,
            max_snapshot_fallback_minutes=max_snapshot_fallback_minutes,
            required_top_ranks=required_top_ranks,
            policy_version=policy_version,
        )
    except THSHotV2SourceError:
        pass
    try:
        return _select_sparse_minute(
            work,
            snapshot_min_symbols=snapshot_min_symbols,
            close_cutoff_minute=close_cutoff_minute,
            max_snapshot_fallback_minutes=max_snapshot_fallback_minutes,
            required_top_ranks=required_top_ranks,
            policy_version=policy_version,
        )
    except _NoCompleteMinute:
        return _select_batch_fallback(
            work,
            snapshot_min_symbols=snapshot_min_symbols,
            close_cutoff_minute=close_cutoff_minute,
            max_snapshot_fallback_minutes=max_snapshot_fallback_minutes,
            required_top_ranks=required_top_ranks,
            policy_version=policy_version,
        )


def reassemble_latest_ths_hot_v2(
    raw: pd.DataFrame,
    *,
    source_date: str,
    snapshot_min_symbols: int,
    close_cutoff_minute: int,
    max_snapshot_fallback_minutes: int,
) -> ReassembledTHSHotV2:
    """Reassemble a historical v2 snapshot with complete ranks 1..20."""

    return _reassemble_latest_ths_hot_sparse(
        raw,
        source_date=source_date,
        snapshot_min_symbols=snapshot_min_symbols,
        close_cutoff_minute=close_cutoff_minute,
        max_snapshot_fallback_minutes=max_snapshot_fallback_minutes,
        required_top_ranks=THS_HOT_V2_REQUIRED_TOP_RANKS,
        policy_version="v2",
    )


def reassemble_latest_ths_hot_v3(
    raw: pd.DataFrame,
    *,
    source_date: str,
    snapshot_min_symbols: int,
    close_cutoff_minute: int,
    max_snapshot_fallback_minutes: int,
) -> ReassembledTHSHotV2:
    """Reassemble a v3 snapshot while preserving up to two source rank gaps."""

    return _reassemble_latest_ths_hot_sparse(
        raw,
        source_date=source_date,
        snapshot_min_symbols=snapshot_min_symbols,
        close_cutoff_minute=close_cutoff_minute,
        max_snapshot_fallback_minutes=max_snapshot_fallback_minutes,
        required_top_ranks=THS_HOT_V3_REQUIRED_TOP_RANKS,
        policy_version="v3",
    )


__all__ = [
    "ReassembledTHSHotV2",
    "THS_HOT_V2_BATCH_GAP_SECONDS",
    "THS_HOT_V2_MAX_COMPONENT_SPAN_SECONDS",
    "THS_HOT_V2_MAX_MISSING_RANKS",
    "THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS",
    "THS_HOT_V2_REQUIRED_TOP_RANKS",
    "THS_HOT_V3_BATCH_GAP_SECONDS",
    "THS_HOT_V3_MAX_COMPONENT_SPAN_SECONDS",
    "THS_HOT_V3_MAX_MISSING_RANKS",
    "THS_HOT_V3_MAX_SNAPSHOT_SYMBOLS",
    "THS_HOT_V3_REQUIRED_TOP_RANKS",
    "THSHotV2SourceError",
    "reassemble_latest_ths_hot_v2",
    "reassemble_latest_ths_hot_v3",
]
