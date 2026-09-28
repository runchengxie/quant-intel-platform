"""Validated FMP commodity EOD bars for the US daily report."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests

from daily_messenger.etl.types import QuoteSnapshot

FMP_EOD_URL = "https://financialmodelingprep.com/stable/historical-price-eod/full"
NEW_YORK = ZoneInfo("America/New_York")


def _parse_closes(payload: object, symbol: str, target_date: date) -> dict[str, float]:
    if not isinstance(payload, list):
        raise RuntimeError("FMP response is not a daily bar list")
    rows: dict[str, float] = {}
    for item in payload:
        if not isinstance(item, dict) or item.get("symbol") != symbol:
            continue
        day = item.get("date")
        close = item.get("close")
        if not isinstance(day, str) or not isinstance(close, (int, float)):
            continue
        try:
            parsed_day = date.fromisoformat(day)
        except ValueError:
            continue
        if parsed_day > target_date or not math.isfinite(close) or close <= 0:
            continue
        if day in rows:
            raise RuntimeError("FMP duplicate daily bar")
        rows[day] = float(close)
    return rows


def fetch_fmp_daily_snapshot(
    symbol: str,
    *,
    target_date: date,
    api_key: str,
    completed_after: time | None = None,
) -> QuoteSnapshot:
    """Return a target-date close and return, rejecting absent or unfinished bars."""
    market_now = datetime.now(NEW_YORK)
    if market_now.date() < target_date or (
        market_now.date() == target_date
        and completed_after is not None
        and market_now.time() < completed_after
    ):
        raise RuntimeError("FMP target daily bar is not complete")
    try:
        response = requests.get(
            FMP_EOD_URL,
            params={
                "symbol": symbol,
                "from": (target_date - timedelta(days=7)).isoformat(),
                "to": target_date.isoformat(),
                "apikey": api_key,
            },
            timeout=12,
        )
    except requests.RequestException as exc:
        raise RuntimeError("FMP request failed") from exc
    if response.status_code != 200:
        raise RuntimeError(f"FMP HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("FMP response is not JSON") from exc
    rows = _parse_closes(payload, symbol, target_date)
    target_day = target_date.isoformat()
    if target_day not in rows:
        raise RuntimeError("FMP target date unavailable")
    prior_days = sorted(day for day in rows if day < target_day)
    if not prior_days:
        raise RuntimeError("FMP previous close unavailable")
    previous_day = prior_days[-1]
    if (target_date - date.fromisoformat(previous_day)).days > 4:
        raise RuntimeError("FMP previous close is stale")
    close = rows[target_day]
    return QuoteSnapshot(target_day, close, (close / rows[previous_day] - 1) * 100, f"fmp:{symbol}")
