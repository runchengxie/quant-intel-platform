"""Private Gold API reference windows, not exchange closes or settlements."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

import requests


@dataclass(frozen=True)
class MetalReferenceWindow:
    """Provider segment values; requested boundaries are not quote timestamps."""

    symbol: str
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    retrieved_at: datetime
    actual_quote_time: datetime | None = None


def _price(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError("Gold API price invalid")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise RuntimeError("Gold API price invalid") from None
    if not math.isfinite(number) or number <= 0:
        raise RuntimeError("Gold API price invalid")
    return number


def fetch_reference_window(
    symbol: str, start: datetime, end: datetime, api_key: str
) -> MetalReferenceWindow:
    """Fetch one completed reference window without inventing unit or provenance.

    Private-only: public facts require an independently verified instrument,
    quotation unit and observation-time convention. Free historical endpoints
    have a shared hourly limit; callers must not use this in the retry timer.
    """
    api_key = api_key.strip()
    if symbol not in {"XAU", "XAG"} or not api_key or api_key == "YOUR_GOLD_API_KEY":
        raise ValueError("Gold API symbol or key invalid")
    if start.utcoffset() is None or end.utcoffset() is None or start >= end:
        raise ValueError("Gold API window invalid")
    if end > datetime.now(UTC):
        raise ValueError("Gold API window is not complete")
    if start.microsecond or end.microsecond:
        raise ValueError("Gold API window must use whole seconds")
    params = {"startTimestamp": int(start.timestamp()), "endTimestamp": int(end.timestamp())}
    try:
        response = requests.get(
            f"https://api.gold-api.com/ohlc/{symbol}",
            params=params,
            headers={"x-api-key": api_key},
            timeout=12,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise RuntimeError("Gold API request failed") from None
    if response.status_code != 200:
        raise RuntimeError(f"Gold API HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError("Gold API JSON invalid") from None
    if not isinstance(payload, dict) or any(
        type(payload.get(key)) is not int or payload[key] != value for key, value in params.items()
    ):
        raise RuntimeError("Gold API window invalid")
    opening, high, low, close = (
        _price(payload.get(key)) for key in ("open", "high", "low", "close")
    )
    if not low <= opening <= high or not low <= close <= high:
        raise RuntimeError("Gold API OHLC ordering invalid")
    return MetalReferenceWindow(symbol, start, end, opening, high, low, close, datetime.now(UTC))
