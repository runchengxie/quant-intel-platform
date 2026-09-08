"""Production freshness-carrier validation for DailyWatch20 sparse strict pools."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

THS_HOT_STRICT_V2 = "ths_hot_strict_v2"
THS_HOT_STRICT_V3 = "ths_hot_strict_v3"
_MINUTE_SOURCES = frozenset({"canonical", "tushare_operational", "tushare_sh_sz_overlay"})


class DailyWatch20FreshnessError(ValueError):
    """Raised when receipt freshness does not bind the production candidate pool."""


def _date_key(value: object, *, field: str) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise DailyWatch20FreshnessError(f"receipt.input_freshness.{field} is invalid")
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise DailyWatch20FreshnessError(f"receipt.input_freshness.{field} is invalid") from exc
    return text


def _validate_minute_binding(receipt: Mapping[str, Any], freshness: Mapping[str, Any]) -> None:
    minute = receipt.get("minute_features")
    if not isinstance(minute, Mapping):
        raise DailyWatch20FreshnessError("receipt.minute_features is required")
    freshness_required = _date_key(
        freshness.get("required_minute_date"), field="required_minute_date"
    )
    minute_required = _date_key(minute.get("required_date"), field="minute_features.required_date")
    if freshness_required != minute_required:
        raise DailyWatch20FreshnessError(
            "receipt.input_freshness.required_minute_date mismatch minute_features.required_date"
        )
    if freshness.get("minute_source") not in _MINUTE_SOURCES:
        raise DailyWatch20FreshnessError("receipt.input_freshness.minute_source is invalid")
    canonical_max = freshness.get("canonical_minute_date_max")
    if canonical_max not in {None, ""}:
        _date_key(canonical_max, field="canonical_minute_date_max")


def validate_sparse_input_freshness(
    receipt: Mapping[str, Any], *, source_date: str, signal_date: str, expected_mode: str
) -> None:
    freshness = receipt.get("input_freshness")
    if not isinstance(freshness, Mapping):
        raise DailyWatch20FreshnessError("receipt.input_freshness is required")
    if freshness.get("status") != "ready":
        raise DailyWatch20FreshnessError("receipt.input_freshness.status must be ready")
    if freshness.get("require_current") is not True:
        raise DailyWatch20FreshnessError("receipt.input_freshness.require_current must be true")
    if freshness.get("reasons") != []:
        raise DailyWatch20FreshnessError("receipt.input_freshness.reasons must be empty")
    expected_dates = {
        "source_date": source_date,
        "signal_date": signal_date,
        "daily_as_of": source_date,
    }
    for field, expected in expected_dates.items():
        if _date_key(freshness.get(field), field=field) != expected:
            raise DailyWatch20FreshnessError(f"receipt.input_freshness.{field} must be {expected}")
    candidate_pool = receipt.get("candidate_pool")
    if not isinstance(candidate_pool, Mapping):
        raise DailyWatch20FreshnessError("receipt.candidate_pool is required")
    if (
        freshness.get("candidate_pool_mode") != expected_mode
        or candidate_pool.get("mode") != expected_mode
    ):
        raise DailyWatch20FreshnessError(
            f"receipt.input_freshness.candidate_pool_mode must be {expected_mode}"
        )
    if freshness.get("candidate_pool_policy_id") != candidate_pool.get("policy_id"):
        raise DailyWatch20FreshnessError(
            "receipt.input_freshness.candidate_pool_policy_id mismatch"
        )
    try:
        freshness_symbols = int(str(freshness.get("candidate_pool_symbols")))
        pool_symbols = int(str(candidate_pool.get("pool_symbols")))
    except (TypeError, ValueError) as exc:
        raise DailyWatch20FreshnessError(
            "receipt.input_freshness.candidate_pool_symbols is invalid"
        ) from exc
    if (
        isinstance(freshness.get("candidate_pool_symbols"), bool)
        or isinstance(candidate_pool.get("pool_symbols"), bool)
        or freshness_symbols != pool_symbols
    ):
        raise DailyWatch20FreshnessError("receipt.input_freshness.candidate_pool_symbols mismatch")
    _validate_minute_binding(receipt, freshness)


def validate_v2_input_freshness(
    receipt: Mapping[str, Any], *, source_date: str, signal_date: str
) -> None:
    validate_sparse_input_freshness(
        receipt,
        source_date=source_date,
        signal_date=signal_date,
        expected_mode=THS_HOT_STRICT_V2,
    )


def validate_v3_input_freshness(
    receipt: Mapping[str, Any], *, source_date: str, signal_date: str
) -> None:
    validate_sparse_input_freshness(
        receipt,
        source_date=source_date,
        signal_date=signal_date,
        expected_mode=THS_HOT_STRICT_V3,
    )


__all__ = [
    "DailyWatch20FreshnessError",
    "validate_sparse_input_freshness",
    "validate_v2_input_freshness",
    "validate_v3_input_freshness",
]
