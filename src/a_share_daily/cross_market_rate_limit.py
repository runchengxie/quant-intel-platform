"""Bounded cooldown policy; persistence belongs to deployment orchestration."""

import os
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any


def next_retry_at(observed_at: datetime, failures: int, retry_after: str | None) -> datetime:
    if observed_at.tzinfo is None:
        raise ValueError("cooldown requires aware observation time")
    if retry_after:
        try:
            result = (
                observed_at + timedelta(seconds=max(0, int(retry_after)))
                if retry_after.strip().isdigit()
                else parsedate_to_datetime(retry_after)
            )
            if result.tzinfo is not None and result > observed_at:
                return result
        except (ValueError, TypeError, OverflowError):
            pass
    return observed_at + timedelta(minutes=min(60, 15 * 2 ** min(2, max(0, failures - 1))))


def cooldown_active() -> bool:
    try:
        value = datetime.fromisoformat(os.environ.get("CROSS_MARKET_YAHOO_COOLDOWN_UNTIL", ""))
        return value.tzinfo is not None and value > datetime.now(UTC)
    except ValueError:
        return False


def is_rate_limited(exc: Exception) -> bool:
    return type(exc).__name__ == "YFRateLimitError"


def serial_quote(yf: Any, symbol: str, window: dict) -> Any:
    """Ticker.history preserves typed failures hidden by batch download."""
    if not hasattr(yf, "Ticker"):
        return yf.download(
            [symbol], **window, progress=False, auto_adjust=False, threads=False, timeout=10
        )
    import pandas as pd

    options = {key: value for key, value in window.items() if key != "ignore_tz"}
    data = yf.Ticker(symbol).history(**options, auto_adjust=False, timeout=10, raise_errors=True)
    return pd.concat({symbol: data}, axis=1).swaplevel(axis=1)


def limited_quote() -> dict:
    observed = datetime.now(UTC)
    try:
        failures = max(0, int(os.environ.get("CROSS_MARKET_YAHOO_FAILURES", "0"))) + 1
    except ValueError:
        failures = 1
    retry_at = next_retry_at(observed, failures, None).isoformat()
    os.environ["CROSS_MARKET_YAHOO_COOLDOWN_UNTIL"] = retry_at
    return {
        "error": "yahoo rate limited",
        "rate_limited": True,
        "retry_at": retry_at,
        "rate_limit_observed_at": observed.isoformat(),
    }
