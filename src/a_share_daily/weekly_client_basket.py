"""Compose and persist the weekly ten-stock client basket."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "a_share_daily.weekly_client_basket.v1"
OFFICIAL_CASHFLOW_SCHEMA = "strategy_app.cashflow.official_top6.v1"
OFFICIAL_CASHFLOW_STRATEGY = "cni_980092_official_top6_v1"
OFFICIAL_CASHFLOW_INDEX = "980092.SZ"
DATE_RE = re.compile(r"^\d{8}$")
SLEEVE_ORDER = ("dailywatch_family", "cashflow", "microcap")


class WeeklyBasketError(ValueError):
    """Raised when a weekly basket cannot be built safely."""


@dataclass(frozen=True)
class SourcePosition:
    symbol: str
    name: str
    source_strategy: str
    source_product: str
    signal_date: str
    valid_until: str | None
    rank: int | None
    score: float | None
    selection_reason: str
    artifact_path: str
    artifact_sha256: str
    research_only: bool
    eligible_for_live: bool


@dataclass(frozen=True)
class BasketPosition(SourcePosition):
    status: str = "NEW"


@dataclass(frozen=True)
class BasketConfig:
    quotas: Mapping[str, int] = field(
        default_factory=lambda: {
            "dailywatch_family": 0,
            "cashflow": 6,
            "microcap": 4,
        }
    )
    allow_microcap_shadow: bool = True
    dedupe_priority: tuple[str, ...] = SLEEVE_ORDER


@dataclass(frozen=True)
class TradeDelta:
    added: tuple[BasketPosition, ...]
    kept: tuple[BasketPosition, ...]
    dropped: tuple[BasketPosition, ...]


@dataclass(frozen=True)
class BasketArtifact:
    report_date: str
    positions: tuple[BasketPosition, ...]
    trade_delta: TradeDelta
    config: BasketConfig
    source_inputs: tuple[dict[str, Any], ...]
    schema_version: str = SCHEMA_VERSION


def _date(value: str, *, label: str) -> str:
    normalized = str(value or "").replace("-", "")
    if not DATE_RE.fullmatch(normalized):
        raise WeeklyBasketError(f"{label} must use YYYYMMDD")
    return normalized


def _hash(value: str, *, label: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise WeeklyBasketError(f"{label} must be a lowercase SHA-256 hash")
    return value.lower()


def _validate_position(position: SourcePosition, *, as_of_date: str, sleeve: str) -> None:
    if position.source_strategy != sleeve:
        raise WeeklyBasketError(
            f"source strategy mismatch: key={sleeve!r}, value={position.source_strategy!r}"
        )
    if not position.symbol.strip():
        raise WeeklyBasketError(f"{sleeve} contains an empty symbol")
    _date(position.signal_date, label=f"{sleeve} signal_date")
    if position.valid_until is not None:
        valid_until = _date(position.valid_until, label=f"{sleeve} valid_until")
        if valid_until < as_of_date:
            raise WeeklyBasketError(
                f"{sleeve} artifact for {position.symbol} expired on {valid_until}"
            )
    _hash(position.artifact_sha256, label=f"{sleeve} artifact_sha256")


def _position_payload(position: SourcePosition | BasketPosition) -> dict[str, Any]:
    return asdict(position)


def _previous_symbols(previous_basket: BasketArtifact | None) -> set[str]:
    if previous_basket is None:
        return set()
    return {position.symbol for position in previous_basket.positions}


def _source_inputs(
    source_positions: Mapping[str, Sequence[SourcePosition]],
    config: BasketConfig,
) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    for sleeve in SLEEVE_ORDER:
        rows = source_positions.get(sleeve, ()) if config.quotas[sleeve] else ()
        if rows:
            values.extend(
                {
                    "sleeve": sleeve,
                    "artifact_path": row.artifact_path,
                    "artifact_sha256": row.artifact_sha256,
                }
                for row in rows
            )
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in values:
        unique[(row["sleeve"], row["artifact_path"])] = row
    return tuple(unique.values())


def compose_weekly_basket(
    source_positions: Mapping[str, Sequence[SourcePosition]],
    *,
    as_of_date: str,
    previous_basket: BasketArtifact | None = None,
    config: BasketConfig | None = None,
) -> BasketArtifact:
    """Select exactly ten distinct positions from the configured sleeves."""
    report_date = _date(as_of_date, label="as_of_date")
    config = config or BasketConfig()
    if tuple(config.dedupe_priority) != SLEEVE_ORDER:
        raise WeeklyBasketError("dedupe_priority must contain the canonical sleeve order")
    if set(config.quotas) != set(SLEEVE_ORDER):
        raise WeeklyBasketError("quotas must define dailywatch_family, cashflow, and microcap")
    if sum(config.quotas.values()) != 10:
        raise WeeklyBasketError("quotas must sum to 10")
    if any(value < 0 for value in config.quotas.values()):
        raise WeeklyBasketError("quotas cannot be negative")

    selected: list[BasketPosition] = []
    used: set[str] = set()
    for sleeve in config.dedupe_priority:
        candidates = list(source_positions.get(sleeve, ()))
        if len({row.symbol for row in candidates}) != len(candidates):
            raise WeeklyBasketError(f"{sleeve} candidates contain duplicate symbols")
        for candidate in candidates:
            _validate_position(candidate, as_of_date=report_date, sleeve=sleeve)
        quota = config.quotas[sleeve]
        for candidate in candidates:
            if len([row for row in selected if row.source_strategy == sleeve]) >= quota:
                break
            if candidate.symbol in used:
                continue
            selected.append(BasketPosition(**asdict(candidate)))
            used.add(candidate.symbol)
        sleeve_count = sum(row.source_strategy == sleeve for row in selected)
        if sleeve_count != quota:
            raise WeeklyBasketError(
                f"{sleeve} has only {sleeve_count} distinct valid candidates; "
                f"cannot build 10 distinct positions"
            )

    if len(selected) != 10 or len(used) != 10:
        raise WeeklyBasketError("weekly basket must contain exactly 10 distinct positions")

    previous_symbols = _previous_symbols(previous_basket)
    selected = [
        replace(position, status="KEEP" if position.symbol in previous_symbols else "NEW")
        for position in selected
    ]
    current_symbols = {position.symbol for position in selected}
    dropped = tuple(
        replace(position, status="DROP")
        for position in (previous_basket.positions if previous_basket else ())
        if position.symbol not in current_symbols
    )
    added = tuple(position for position in selected if position.status == "NEW")
    kept = tuple(position for position in selected if position.status == "KEEP")
    return BasketArtifact(
        report_date=report_date,
        positions=tuple(selected),
        trade_delta=TradeDelta(added=added, kept=kept, dropped=dropped),
        config=config,
        source_inputs=_source_inputs(source_positions, config),
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, BasketConfig):
        return {"quotas": dict(value.quotas), "allow_microcap_shadow": value.allow_microcap_shadow}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    return value


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        _json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _basket_payload(artifact: BasketArtifact) -> dict[str, Any]:
    return {
        "schema_version": artifact.schema_version,
        "report_date": artifact.report_date,
        "config": _json_safe(artifact.config),
        "positions": [_position_payload(row) for row in artifact.positions],
        "trade_delta": _json_safe(artifact.trade_delta),
        "source_inputs": list(artifact.source_inputs),
    }


def _csv_payload(artifact: BasketArtifact) -> str:
    output = io.StringIO(newline="")
    fields = [
        "symbol",
        "name",
        "source_strategy",
        "source_product",
        "status",
        "signal_date",
        "valid_until",
        "rank",
        "score",
        "research_only",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for position in artifact.positions:
        row = _position_payload(position)
        writer.writerow({field: row[field] for field in fields})
    return output.getvalue()


def write_basket_artifacts(artifact: BasketArtifact, output_root: Path) -> dict[str, Path]:
    """Write the machine-readable snapshot and immutable build receipt."""
    directory = output_root / artifact.report_date
    basket_path = directory / "basket.json"
    csv_path = directory / "basket.csv"
    delta_path = directory / "trade_delta.json"
    receipt_path = directory / "receipt.json"
    latest_path = output_root / "latest.json"
    payload = _basket_payload(artifact)
    basket_bytes = _canonical_json(payload) + b"\n"
    basket_hash = hashlib.sha256(basket_bytes).hexdigest()
    delta_bytes = _canonical_json(artifact.trade_delta) + b"\n"
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "report_date": artifact.report_date,
        "status": "built",
        "send_status": "not_requested",
        "basket_sha256": basket_hash,
        "source_inputs": list(artifact.source_inputs),
        "config": _json_safe(artifact.config),
    }
    _atomic_write(basket_path, basket_bytes)
    _atomic_write(latest_path, basket_bytes)
    _atomic_write(csv_path, _csv_payload(artifact).encode("utf-8"))
    _atomic_write(delta_path, delta_bytes)
    _atomic_write(receipt_path, _canonical_json(receipt) + b"\n")
    return {
        "basket": basket_path,
        "csv": csv_path,
        "delta": delta_path,
        "receipt": receipt_path,
        "latest": latest_path,
    }


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    value = _read_json_value(path, label=label)
    if not isinstance(value, dict):
        raise WeeklyBasketError(f"{label} must be a JSON object")
    return value


def _read_json_value(path: Path, *, label: str) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WeeklyBasketError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WeeklyBasketError(f"{label} is not valid JSON: {path}") from exc
    return value


def _rows(value: Any, *, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise WeeklyBasketError(f"{label} must be a list of objects")
    return cast(list[Mapping[str, Any]], value)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_position(
    row: Mapping[str, Any],
    *,
    strategy: str,
    product: str,
    signal_date: str,
    valid_until: str | None,
    artifact_path: Path,
    artifact_sha256: str,
    research_only: bool,
    eligible_for_live: bool,
    default_reason: str,
) -> SourcePosition:
    return SourcePosition(
        symbol=str(row.get("symbol") or row.get("ts_code") or "").strip(),
        name=str(row.get("name") or row.get("symbol") or row.get("ts_code") or "").strip(),
        source_strategy=strategy,
        source_product=product,
        signal_date=signal_date,
        valid_until=valid_until,
        rank=(
            int(row["rank"])
            if row.get("rank") is not None
            else int(row["official_rank"])
            if row.get("official_rank") is not None
            else int(row["model_rank"])
            if row.get("model_rank") is not None
            else int(row["selection_rank"])
            if row.get("selection_rank") is not None
            else None
        ),
        score=(
            float(row["score"])
            if row.get("score") is not None
            else float(row["official_weight"])
            if row.get("official_weight") is not None
            else float(row["score_D11_20"])
            if row.get("score_D11_20") is not None
            else float(row["score_percentile"])
            if row.get("score_percentile") is not None
            else float(row["selection_score"])
            if row.get("selection_score") is not None
            else float(row["final_score"])
            if row.get("final_score") is not None
            else None
        ),
        selection_reason=str(row.get("selection_reason") or default_reason),
        artifact_path=str(artifact_path),
        artifact_sha256=artifact_sha256,
        research_only=research_only,
        eligible_for_live=eligible_for_live,
    )


def enrich_source_names(
    source_positions: Mapping[str, Sequence[SourcePosition]],
    names_by_symbol: Mapping[str, str],
) -> dict[str, list[SourcePosition]]:
    """Fill code-only display names from a pinned instrument snapshot."""
    normalized = {
        str(symbol).strip().upper(): str(name).strip()
        for symbol, name in names_by_symbol.items()
        if str(name).strip()
    }
    enriched: dict[str, list[SourcePosition]] = {}
    for sleeve, positions in source_positions.items():
        rows: list[SourcePosition] = []
        for position in positions:
            current_name = position.name.strip()
            name = normalized.get(position.symbol.strip().upper())
            rows.append(
                replace(position, name=name)
                if name and (not current_name or current_name == position.symbol)
                else position
            )
        enriched[sleeve] = rows
    return enriched


def filter_source_positions_by_instruments(
    source_positions: Mapping[str, Sequence[SourcePosition]],
    instruments_by_symbol: Mapping[str, Mapping[str, Any]],
    *,
    as_of_date: str,
) -> dict[str, list[SourcePosition]]:
    """Keep securities that were listed and not delisted on the report date."""
    report_date = _date(as_of_date, label="as_of_date")
    normalized = {
        str(symbol).strip().upper(): instrument
        for symbol, instrument in instruments_by_symbol.items()
    }
    filtered: dict[str, list[SourcePosition]] = {}

    def instrument_text(instrument: Mapping[str, Any], key: str) -> str:
        text = str(instrument.get(key) or "").strip()
        return "" if text.lower() in {"nan", "nat", "none"} else text

    for sleeve, positions in source_positions.items():
        rows: list[SourcePosition] = []
        for position in positions:
            instrument = normalized.get(position.symbol.strip().upper())
            if instrument is None:
                continue
            list_date = instrument_text(instrument, "list_date")
            delist_date = instrument_text(instrument, "delist_date")
            if list_date and list_date > report_date:
                continue
            if delist_date and delist_date <= report_date:
                continue
            list_status = str(instrument.get("list_status") or "").strip().upper()
            if list_status != "L" and not (delist_date and delist_date > report_date):
                continue
            rows.append(position)
        filtered[sleeve] = rows
    return filtered


def load_dailywatch_family(path: Path, *, as_of_date: str) -> list[SourcePosition]:
    """Load D11-H5 or DailyWatch20 structured positions for the family sleeve."""
    report_date = _date(as_of_date, label="as_of_date")
    raw = _read_json_value(path, label="DailyWatch family artifact")
    if isinstance(raw, list):
        rows = _rows(raw, label="DailyWatch positions")
        if not rows:
            raise WeeklyBasketError("DailyWatch family artifact contains no positions")
        artifact: dict[str, Any] = {}
        product = "daily_watch20"
        signal_date = _date(str(rows[0].get("signal_date") or ""), label="signal_date")
    elif isinstance(raw, dict):
        artifact = raw
        if artifact.get("status") not in (None, "passed"):
            raise WeeklyBasketError("DailyWatch family artifact is not passed")
        signal = artifact.get("signal")
        if isinstance(signal, Mapping) and signal.get("positions") is not None:
            rows = _rows(signal["positions"], label="DailyWatch signal.positions")
            product = "d11_h5_shadow"
            signal_date = _date(str(artifact.get("signal_date") or ""), label="signal_date")
        else:
            rows = _rows(
                artifact.get("positions", artifact.get("candidates")),
                label="DailyWatch positions",
            )
            product = str(artifact.get("product_id") or "daily_watch20")
            signal_date = _date(
                str(artifact.get("signal_date") or artifact.get("source_date") or ""),
                label="signal_date",
            )
    else:
        raise WeeklyBasketError("DailyWatch family artifact must be a JSON object or array")
    if signal_date > report_date:
        raise WeeklyBasketError("DailyWatch family signal_date is after as_of_date")
    digest = _file_hash(path)
    result = [
        _row_position(
            row,
            strategy="dailywatch_family",
            product=product,
            signal_date=signal_date,
            valid_until=artifact.get("valid_until"),
            artifact_path=path,
            artifact_sha256=digest,
            research_only=bool(artifact.get("research_only", product != "daily_watch20")),
            eligible_for_live=bool(artifact.get("eligible_for_live", product == "daily_watch20")),
            default_reason="DailyWatch family structured selection",
        )
        for row in rows
    ]
    if not result or any(not row.symbol for row in result):
        raise WeeklyBasketError("DailyWatch family artifact contains no valid positions")
    return result


def _validate_official_cashflow_contract(
    artifact: Mapping[str, Any], receipt: Mapping[str, Any], *, report_date: str
) -> tuple[str, str, list[Mapping[str, Any]]]:
    identity = {
        "schema_version": OFFICIAL_CASHFLOW_SCHEMA,
        "strategy_id": OFFICIAL_CASHFLOW_STRATEGY,
        "index_code": OFFICIAL_CASHFLOW_INDEX,
    }
    if any(artifact.get(key) != value for key, value in identity.items()):
        raise WeeklyBasketError("Cashflow selection must use the official CNI 980092 Top 6")
    if any(receipt.get(key) != value for key, value in identity.items()):
        raise WeeklyBasketError("Cashflow publication receipt must match the official CNI Top 6")
    if artifact.get("status") != "passed" or not artifact.get("research_only"):
        raise WeeklyBasketError("Cashflow selection must be a passed research artifact")
    if artifact.get("eligible_for_live") is not False:
        raise WeeklyBasketError("Cashflow selection must remain ineligible for live use")
    if (
        receipt.get("status") != "passed"
        or receipt.get("research_only") is not True
        or receipt.get("eligible_for_live") is not False
    ):
        raise WeeklyBasketError("Cashflow publication receipt is not passed")
    signal_date = _date(str(artifact.get("report_date") or ""), label="Cashflow report_date")
    receipt_date = _date(str(receipt.get("report_date") or ""), label="Cashflow receipt date")
    if signal_date != report_date or receipt_date != report_date:
        raise WeeklyBasketError("Cashflow report_date must match as_of_date")
    snapshot_date = _date(
        str(artifact.get("official_snapshot_date") or ""),
        label="Cashflow official_snapshot_date",
    )
    receipt_snapshot_date = _date(
        str(receipt.get("official_snapshot_date") or ""),
        label="Cashflow receipt official_snapshot_date",
    )
    if snapshot_date > report_date:
        raise WeeklyBasketError("Cashflow official snapshot is after as_of_date")
    if receipt_snapshot_date != snapshot_date:
        raise WeeklyBasketError("Cashflow receipt snapshot does not match selection")
    rows = _rows(artifact.get("targets"), label="Cashflow targets")
    if artifact.get("selected_count") != 6 or receipt.get("selected_count") != 6 or len(rows) != 6:
        raise WeeklyBasketError("official CNI Cashflow selection must contain exactly six targets")
    if receipt.get("gates") != {"snapshot_complete": "passed", "top6_listed": "passed"}:
        raise WeeklyBasketError("official CNI Cashflow receipt gates are not passed")
    symbols = [str(row.get("symbol") or "").strip().upper() for row in rows]
    ranks = [row.get("official_rank") for row in rows]
    weights = [row.get("official_weight") for row in rows]
    if len(set(symbols)) != 6 or "" in symbols or ranks != list(range(1, 7)):
        raise WeeklyBasketError("official CNI Cashflow targets are incomplete or out of rank order")
    if any(
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not math.isfinite(weight)
        or weight <= 0
        for weight in weights
    ):
        raise WeeklyBasketError("official CNI Cashflow weights must be positive numbers")
    return signal_date, snapshot_date, rows


def load_cashflow_selection(
    selection_path: Path,
    publication_receipt_path: Path,
    *,
    as_of_date: str,
) -> list[SourcePosition]:
    """Load a passed, research-only Cashflow selection and its publication receipt."""
    report_date = _date(as_of_date, label="as_of_date")
    artifact = _read_json_object(selection_path, label="Cashflow selection")
    receipt = _read_json_object(publication_receipt_path, label="Cashflow publication receipt")
    signal_date, snapshot_date, rows = _validate_official_cashflow_contract(
        artifact, receipt, report_date=report_date
    )
    digest = _file_hash(selection_path)
    if receipt.get("selection_sha256") != digest:
        raise WeeklyBasketError("Cashflow publication receipt hash mismatch")
    return [
        _row_position(
            row,
            strategy="cashflow",
            product=str(artifact.get("strategy_id") or "cashflow_quality_top50_v1"),
            signal_date=signal_date,
            valid_until=(
                str(artifact.get("valid_until"))
                if artifact.get("valid_until") is not None
                else str(artifact.get("next_rebalance_date"))
                if artifact.get("next_rebalance_date") is not None
                else None
            ),
            artifact_path=selection_path,
            artifact_sha256=digest,
            research_only=True,
            eligible_for_live=False,
            default_reason=f"Official CNI 980092 weight rank on {snapshot_date}",
        )
        for row in rows
    ]


def _validate_microcap_v2(
    artifact: Mapping[str, Any],
    *,
    path: Path,
    receipt_path: Path | None,
    report_date: str,
    signal_date: str,
) -> None:
    if receipt_path is None:
        raise WeeklyBasketError("Microcap v2 publication receipt is required")
    receipt = _read_json_object(receipt_path, label="Microcap publication receipt")
    if (
        receipt.get("schema_version") != "microcap.selection.receipt.v2"
        or receipt.get("status") != "passed"
        or receipt.get("research_only") is not True
        or receipt.get("eligible_for_live") is not False
    ):
        raise WeeklyBasketError("Microcap publication receipt is not passed")
    validity = (
        _date(str(artifact.get("valid_from") or ""), label="Microcap valid_from"),
        _date(str(artifact.get("valid_until") or ""), label="Microcap valid_until"),
    )
    receipt_validity = (
        _date(str(receipt.get("valid_from") or ""), label="Microcap receipt valid_from"),
        _date(str(receipt.get("valid_until") or ""), label="Microcap receipt valid_until"),
    )
    if validity != receipt_validity or not validity[0] <= report_date <= validity[1]:
        raise WeeklyBasketError("Microcap selection validity does not cover as_of_date")
    if receipt.get("signal_date") != signal_date:
        raise WeeklyBasketError("Microcap receipt signal date mismatch")
    if receipt.get("artifact_sha256") != _file_hash(path):
        raise WeeklyBasketError("Microcap publication receipt hash mismatch")


def load_microcap_selection(
    path: Path,
    *,
    as_of_date: str,
    receipt_path: Path | None = None,
    shadow: bool = True,
    allow_legacy: bool = False,
) -> list[SourcePosition]:
    """Load a microcap artifact only when it explicitly declares shadow status."""
    report_date = _date(as_of_date, label="as_of_date")
    artifact = _read_json_object(path, label="Microcap selection")
    schema = artifact.get("schema_version")
    if schema == "microcap.selection.v1" and not allow_legacy:
        raise WeeklyBasketError("Microcap selection v1 is allowed only for legacy diagnostics")
    if schema not in {"microcap.selection.v1", "microcap.selection.v2"}:
        raise WeeklyBasketError("Microcap selection schema is unsupported")
    if not shadow or artifact.get("shadow") is not True:
        raise WeeklyBasketError("Microcap selection requires an explicit shadow marker")
    if artifact.get("status") not in (None, "passed"):
        raise WeeklyBasketError("Microcap selection is not passed")
    if artifact.get("research_only") is not True or artifact.get("eligible_for_live") is not False:
        raise WeeklyBasketError("Microcap selection must remain research-only")
    signal_date = _date(
        str(artifact.get("signal_date") or artifact.get("source_date") or ""),
        label="Microcap signal_date",
    )
    if signal_date > report_date:
        raise WeeklyBasketError("Microcap signal_date is after as_of_date")
    if schema == "microcap.selection.v2":
        _validate_microcap_v2(
            artifact,
            path=path,
            receipt_path=receipt_path,
            report_date=report_date,
            signal_date=signal_date,
        )
    rows = _rows(
        artifact.get("positions", artifact.get("targets")),
        label="Microcap positions",
    )
    minimum_candidates = 10 if schema == "microcap.selection.v2" else 3
    if len(rows) < minimum_candidates:
        raise WeeklyBasketError(
            f"Microcap selection must contain at least {minimum_candidates} candidates"
        )
    digest = _file_hash(path)
    return [
        _row_position(
            row,
            strategy="microcap",
            product=str(artifact.get("product_id") or "microcap_shadow"),
            signal_date=signal_date,
            valid_until=artifact.get("valid_until"),
            artifact_path=path,
            artifact_sha256=digest,
            research_only=True,
            eligible_for_live=False,
            default_reason="Microcap research shadow selection",
        )
        for row in rows
    ]


def basket_artifact_from_payload(payload: Mapping[str, Any]) -> BasketArtifact:
    """Validate and load one canonical basket payload."""
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise WeeklyBasketError("previous basket schema is unsupported")
    report_date = _date(str(payload.get("report_date") or ""), label="previous report_date")
    positions = []
    for row in _rows(payload.get("positions"), label="previous positions"):
        try:
            positions.append(BasketPosition(**row))
        except TypeError as exc:
            raise WeeklyBasketError("previous basket position is malformed") from exc
    if len(positions) != 10 or len({position.symbol for position in positions}) != 10:
        raise WeeklyBasketError("previous basket must contain 10 distinct positions")
    config_payload = payload.get("config")
    if not isinstance(config_payload, Mapping):
        raise WeeklyBasketError("previous basket config is missing")
    config = BasketConfig(
        quotas=dict(config_payload.get("quotas", {})),
        allow_microcap_shadow=bool(config_payload.get("allow_microcap_shadow", True)),
    )
    delta_payload = payload.get("trade_delta", {})
    if not isinstance(delta_payload, Mapping):
        raise WeeklyBasketError("previous basket trade_delta is malformed")

    def delta_rows(label: str) -> tuple[BasketPosition, ...]:
        try:
            return tuple(BasketPosition(**row) for row in delta_payload.get(label, ()))
        except TypeError as exc:
            raise WeeklyBasketError("previous basket trade_delta is malformed") from exc

    return BasketArtifact(
        report_date=report_date,
        positions=tuple(positions),
        trade_delta=TradeDelta(
            added=delta_rows("added"),
            kept=delta_rows("kept"),
            dropped=delta_rows("dropped"),
        ),
        config=config,
        source_inputs=tuple(payload.get("source_inputs", ())),
    )


def load_previous_basket(path: Path) -> BasketArtifact:
    """Load a previously written canonical basket for NEW/KEEP/DROP diffing."""
    return basket_artifact_from_payload(_read_json_object(path, label="previous basket"))


__all__ = [
    "BasketArtifact",
    "BasketConfig",
    "BasketPosition",
    "SourcePosition",
    "TradeDelta",
    "WeeklyBasketError",
    "basket_artifact_from_payload",
    "compose_weekly_basket",
    "enrich_source_names",
    "filter_source_positions_by_instruments",
    "load_cashflow_selection",
    "load_dailywatch_family",
    "load_microcap_selection",
    "load_previous_basket",
    "write_basket_artifacts",
]
