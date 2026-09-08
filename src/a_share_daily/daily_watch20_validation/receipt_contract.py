"""Receipt-level validation contracts for DailyWatch20.

Pure physical split of ``a_share_daily.daily_watch20``; see ``_common`` for the
shared base helpers and constants.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd

from ..daily_watch20_policy import (
    StrategyPolicyValidationError,
    validate_strategy_policy_v2,
)
from ._common import (
    WATCHLIST_SCHEMA_V2,
    WATCHLIST_SCHEMAS,
    WEIGHT_TOLERANCE,
    DailyWatch20ValidationError,
    _normalize_market_scope,
    _receipt_date,
)


def _validate_generated_at(receipt: Mapping[str, Any]) -> None:
    raw = str(receipt.get("generated_at") or "").strip()
    if not raw:
        raise DailyWatch20ValidationError("receipt.generated_at is required")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DailyWatch20ValidationError("receipt.generated_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DailyWatch20ValidationError("receipt.generated_at must include a timezone")
    if parsed.tzinfo is not None and parsed.astimezone(UTC) > datetime.now(UTC) + timedelta(
        minutes=5
    ):
        raise DailyWatch20ValidationError("receipt.generated_at is in the future")


def _validate_receipt_contract(receipt: Mapping[str, Any]) -> tuple[str, str, str]:
    schema_version = str(receipt.get("schema_version") or "")
    if schema_version not in WATCHLIST_SCHEMAS:
        supported = ", ".join(sorted(WATCHLIST_SCHEMAS))
        raise DailyWatch20ValidationError(f"receipt.schema_version must be one of: {supported}")
    if str(receipt.get("status") or "").strip().lower() != "passed":
        raise DailyWatch20ValidationError("receipt.status is not passed")
    quality = str(receipt.get("quality_status") or "passed").strip().lower()
    if quality != "passed":
        raise DailyWatch20ValidationError("receipt.quality_status is not passed")
    if _normalize_market_scope(receipt.get("market_scope")) != "sh-sz":
        raise DailyWatch20ValidationError("receipt.market_scope must be sh-sz")
    _validate_generated_at(receipt)
    source_date = _receipt_date(receipt, "source_date")
    signal_date = _receipt_date(receipt, "signal_date")
    if signal_date <= source_date:
        raise DailyWatch20ValidationError("receipt.signal_date must be after source_date")
    if schema_version == WATCHLIST_SCHEMA_V2:
        try:
            validate_strategy_policy_v2(receipt)
        except StrategyPolicyValidationError as exc:
            raise DailyWatch20ValidationError(str(exc)) from exc
    return source_date, signal_date, schema_version


def _validate_receipt_totals(receipt: Mapping[str, Any]) -> None:
    counts = receipt.get("counts")
    if not isinstance(counts, Mapping):
        raise DailyWatch20ValidationError("receipt.counts is required")
    expected = {"total": 20, "a": 4, "b": 16, "unique": 20}
    for key, value in expected.items():
        raw_count = counts.get(key)
        if raw_count is None:
            raise DailyWatch20ValidationError(f"receipt.counts.{key} is invalid")
        try:
            actual = int(str(raw_count))
        except (TypeError, ValueError) as exc:
            raise DailyWatch20ValidationError(f"receipt.counts.{key} is invalid") from exc
        if actual != value:
            raise DailyWatch20ValidationError(f"receipt.counts.{key} must be {value}, got {actual}")
    raw_weight_sum = receipt.get("tracking_weight_sum")
    try:
        weight_sum = float(str(raw_weight_sum))
    except (TypeError, ValueError) as exc:
        raise DailyWatch20ValidationError("receipt.tracking_weight_sum is invalid") from exc
    if not math.isclose(weight_sum, 1.0, abs_tol=WEIGHT_TOLERANCE):
        raise DailyWatch20ValidationError(
            f"receipt.tracking_weight_sum must be 1.0, got {weight_sum:.10g}"
        )


def _required_minute_date(calendar_path: Path, source_date: str, lag_trade_days: int) -> str:
    try:
        calendar = pd.read_parquet(calendar_path)
    except (OSError, ValueError) as exc:
        raise DailyWatch20ValidationError(
            f"cannot read trade calendar for minute freshness: {calendar_path}"
        ) from exc
    date_col = "cal_date" if "cal_date" in calendar.columns else "trade_date"
    if date_col not in calendar.columns or "is_open" not in calendar.columns:
        raise DailyWatch20ValidationError("trade calendar must contain cal_date and is_open")
    raw_dates = cast(pd.Series, calendar[date_col])
    raw_flags = cast(pd.Series, calendar["is_open"])
    dates = cast(pd.Series, raw_dates.astype("string").str.replace("-", "", regex=False))
    flags = cast(pd.Series, pd.to_numeric(raw_flags, errors="coerce"))
    valid_dates = cast(pd.Series, dates.str.fullmatch(r"\d{8}"))
    if bool(dates.isna().any()) or not bool(valid_dates.all()) or bool(flags.isna().any()):
        raise DailyWatch20ValidationError("trade calendar contains invalid dates or open flags")
    normalized = pd.DataFrame({"date": dates, "is_open": flags.astype(int)})
    inconsistent = cast(pd.Series, normalized.groupby("date")["is_open"].nunique().gt(1))
    if bool(inconsistent.any()):
        raise DailyWatch20ValidationError("trade calendar contains inconsistent open flags")
    open_date_values = cast(
        pd.Series,
        normalized.loc[normalized["is_open"].eq(1), "date"],
    )
    open_dates = sorted(str(value) for value in open_date_values.unique())
    if source_date not in open_dates:
        raise DailyWatch20ValidationError(
            f"source_date is missing from open trade calendar: {source_date}"
        )
    position = open_dates.index(source_date) - lag_trade_days
    if position < 0:
        raise DailyWatch20ValidationError(
            f"trade calendar has no date at lag {lag_trade_days} before {source_date}"
        )
    return str(open_dates[position])


__all__ = [
    "_validate_generated_at",
    "_validate_receipt_contract",
    "_validate_receipt_totals",
    "_required_minute_date",
]
