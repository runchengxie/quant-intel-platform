"""Fail-closed consumer contract for research-owned weekly ETF artifacts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "weekly_etf_rotation.v2"
ARTIFACT_TYPE = "weekly_etf_rotation"
STRATEGY_ID = "weekly_etf_rotation_v1"
VARIANT_IDS = {
    "weekly_etf_rotation_fixed_slots_v1",
    "weekly_etf_rotation_defensive_v1",
    "weekly_etf_rotation_qp_min_variance_v1",
}
ACTION_STATUSES = {"NEW", "INCREASE", "KEEP", "REDUCE", "EXIT"}
FROZEN_SYMBOLS = {
    "510300",
    "510500",
    "512100",
    "510880",
    "159915",
    "588000",
    "518880",
    "511260",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class WeeklyEtfRotationArtifactError(ValueError):
    """Raised when an ETF artifact is unsafe for consumer rendering."""


@dataclass(frozen=True)
class WeeklyEtfRotationArtifact:
    strategy_id: str
    variant_id: str
    signal_date: str
    data_as_of: str
    execution_window: str
    positions: tuple[dict[str, Any], ...]
    payload: dict[str, Any]


def _date(value: object, field: str) -> str:
    text = str(value or "").strip().replace("-", "")
    try:
        return datetime.strptime(text, "%Y%m%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise WeeklyEtfRotationArtifactError(f"{field} must be YYYYMMDD") from exc


def _sha(value: object) -> str:
    text = str(value or "")
    if SHA256.fullmatch(text) is None:
        raise WeeklyEtfRotationArtifactError("source.input_sha256 must be a lowercase SHA-256")
    return text


def _number(value: object, field: str) -> float:
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise WeeklyEtfRotationArtifactError(f"{field} must be finite") from exc
    if not math.isfinite(number) or number < 0:
        raise WeeklyEtfRotationArtifactError(f"{field} must be finite and non-negative")
    return number


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise WeeklyEtfRotationArtifactError(f"artifact is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeeklyEtfRotationArtifactError(f"cannot read artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise WeeklyEtfRotationArtifactError("artifact must be an object")
    return payload


def _header(payload: dict[str, Any]) -> str:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise WeeklyEtfRotationArtifactError("unsupported weekly ETF artifact schema")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise WeeklyEtfRotationArtifactError("weekly ETF artifact type is invalid")
    if payload.get("strategy_id") != STRATEGY_ID:
        raise WeeklyEtfRotationArtifactError("strategy_id is invalid")
    variant_id = str(payload.get("variant_id") or "")
    if variant_id not in VARIANT_IDS:
        raise WeeklyEtfRotationArtifactError("variant_id is invalid")
    if payload.get("status") != "research_only" or payload.get("research_only") is not True:
        raise WeeklyEtfRotationArtifactError("artifact must be research_only")
    if payload.get("eligible_for_live") is not False:
        raise WeeklyEtfRotationArtifactError("eligible_for_live must be false")
    return variant_id


def _timing(payload: dict[str, Any], expected: str | None) -> tuple[str, str, str]:
    signal = _date(payload.get("signal_date"), "signal_date")
    as_of = _date(payload.get("data_as_of"), "data_as_of")
    if as_of < signal:
        raise WeeklyEtfRotationArtifactError("data_as_of cannot precede signal_date")
    if expected is not None and signal != _date(expected, "expected_signal_date"):
        raise WeeklyEtfRotationArtifactError("signal_date does not match expected signal_date")
    window = str(payload.get("execution_window") or "").strip()
    if not window.startswith("next observed session close"):
        raise WeeklyEtfRotationArtifactError("execution_window is invalid")
    return signal, as_of, window


def _positions(payload: dict[str, Any]) -> tuple[tuple[dict[str, Any], ...], float]:
    rows = payload.get("positions")
    if not isinstance(rows, list) or not rows:
        raise WeeklyEtfRotationArtifactError("positions must be a non-empty list")
    symbols: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise WeeklyEtfRotationArtifactError(f"positions[{index}] must be an object")
        symbol = str(row.get("symbol") or "").strip()
        if not symbol or symbol in symbols:
            raise WeeklyEtfRotationArtifactError("positions must contain unique symbols")
        if symbol not in FROZEN_SYMBOLS:
            raise WeeklyEtfRotationArtifactError(
                f"positions[{index}].symbol is not in frozen universe"
            )
        symbols.add(symbol)
        weight = _number(row.get("target_weight"), f"positions[{index}].target_weight")
        status = str(row.get("status") or "")
        if status not in ACTION_STATUSES:
            raise WeeklyEtfRotationArtifactError(f"positions[{index}].status is invalid")
        normalized.append({**cast(dict[str, Any], row), "symbol": symbol, "target_weight": weight})
    return tuple(normalized), sum(row["target_weight"] for row in normalized)


def _trade_delta(payload: dict[str, Any]) -> None:
    rows = payload.get("trade_delta")
    if not isinstance(rows, list):
        raise WeeklyEtfRotationArtifactError("trade_delta must be a list")
    symbols: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise WeeklyEtfRotationArtifactError(f"trade_delta[{index}] must be an object")
        symbol = str(row.get("symbol") or "").strip()
        if symbol not in FROZEN_SYMBOLS or symbol in symbols:
            raise WeeklyEtfRotationArtifactError(f"trade_delta[{index}].symbol is invalid")
        symbols.add(symbol)
        _number(row.get("previous_weight"), f"trade_delta[{index}].previous_weight")
        _number(row.get("target_weight"), f"trade_delta[{index}].target_weight")
        if row.get("status") not in ACTION_STATUSES:
            raise WeeklyEtfRotationArtifactError(f"trade_delta[{index}].status is invalid")


def _totals(payload: dict[str, Any], total: float) -> None:
    diagnostics = payload.get("portfolio_diagnostics")
    if (
        not isinstance(diagnostics, dict)
        or not math.isclose(
            _number(diagnostics.get("weight_sum"), "portfolio_diagnostics.weight_sum"),
            1.0,
            abs_tol=1e-6,
        )
        or not math.isclose(total, 1.0, abs_tol=1e-6)
    ):
        raise WeeklyEtfRotationArtifactError("portfolio_diagnostics.weight_sum must equal one")
    source = payload.get("source")
    if not isinstance(source, dict):
        raise WeeklyEtfRotationArtifactError("source is required")
    _sha(source.get("input_sha256"))
    if payload.get("trade_delta_basis") not in {"no_previous_target", "previous_artifact_target"}:
        raise WeeklyEtfRotationArtifactError("trade_delta_basis is invalid")


def load_weekly_etf_rotation_artifact(
    path: Path,
    *,
    expected_signal_date: str | None = None,
) -> WeeklyEtfRotationArtifact:
    """Load an ETF artifact for research-only display and shadow observation."""

    path = Path(path)
    payload = _read(path)
    variant_id = _header(payload)
    signal_date, data_as_of, execution_window = _timing(payload, expected_signal_date)
    normalized, total_weight = _positions(payload)
    _totals(payload, total_weight)
    _trade_delta(payload)
    return WeeklyEtfRotationArtifact(
        strategy_id=STRATEGY_ID,
        variant_id=variant_id,
        signal_date=signal_date,
        data_as_of=data_as_of,
        execution_window=execution_window,
        positions=tuple(normalized),
        payload=payload,
    )


__all__ = [
    "WeeklyEtfRotationArtifact",
    "WeeklyEtfRotationArtifactError",
    "load_weekly_etf_rotation_artifact",
]
