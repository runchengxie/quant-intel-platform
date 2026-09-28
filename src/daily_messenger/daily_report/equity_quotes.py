"""Completed US stock daily bars for a fixed watchlist and reviewed movers."""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote

from daily_messenger.etl.config import resolve_api_key
from daily_messenger.etl.fetchers.quotes import fetch_yahoo_daily_snapshot
from daily_messenger.etl.http import request_json
from daily_messenger.etl.types import QuoteSnapshot

from .models import MarketFact

CORE_SYMBOLS = ("MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "META")
ALPACA_SOURCE_URL = "https://docs.alpaca.markets/us/reference/stockbars"
logger = logging.getLogger(__name__)


def _fetch_alpaca_sip_snapshot(
    symbol: str, report_date: date, key_id: str, secret: str
) -> QuoteSnapshot:
    """Use consolidated SIP raw daily bars; never substitute an IEX-only close."""
    payload = request_json(
        "https://data.alpaca.markets/v2/stocks/bars",
        params={
            "symbols": symbol,
            "timeframe": "1Day",
            "start": (report_date - timedelta(days=7)).isoformat(),
            "end": (report_date + timedelta(days=1)).isoformat(),
            "limit": 20,
            "adjustment": "raw",
            "feed": "sip",
        },
        headers={
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        },
    )
    bars_map = payload.get("bars") if isinstance(payload, dict) else None
    bars = bars_map.get(symbol) if isinstance(bars_map, dict) else None
    if not isinstance(bars, list):
        raise ValueError("Alpaca SIP daily bars unavailable")
    valid = sorted(
        (bar for bar in bars if isinstance(bar, dict) and isinstance(bar.get("t"), str)),
        key=lambda bar: bar["t"],
    )
    target = [bar for bar in valid if bar["t"][:10] == report_date.isoformat()]
    previous = [bar for bar in valid if bar["t"][:10] < report_date.isoformat()]
    if len(target) != 1 or not previous:
        raise ValueError("Alpaca SIP target or previous close missing")
    close = target[0].get("c")
    prior = previous[-1].get("c")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        for value in (close, prior)
    ):
        raise ValueError("Alpaca SIP invalid daily close")
    return QuoteSnapshot(
        report_date.isoformat(),
        float(close),
        round((float(close) / float(prior) - 1) * 100, 4),
        "alpaca:sip",
    )


def fetch_equity_facts(
    report_date: date, mover_tickers: tuple[str, ...] = ()
) -> tuple[list[MarketFact], tuple[str, ...]]:
    """Publish per-symbol price and daily move together, or omit that symbol."""
    symbols = tuple(dict.fromkeys((*CORE_SYMBOLS, *mover_tickers)))
    key_id = resolve_api_key("alpaca_key_id")
    secret = resolve_api_key("alpaca_secret")
    now = datetime.now(UTC)
    facts: list[MarketFact] = []
    missing: list[str] = []
    for symbol in symbols:
        if not symbol.isascii() or not symbol.isupper() or not symbol.isalpha() or len(symbol) > 5:
            missing.append(symbol)
            continue
        snapshot = None
        source = "Yahoo Finance"
        url = f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/"
        try:
            snapshot = fetch_yahoo_daily_snapshot(symbol, target_date=report_date)
            if (
                snapshot.day != report_date.isoformat()
                or not math.isfinite(snapshot.close)
                or snapshot.close <= 0
                or not math.isfinite(snapshot.change_pct)
                or abs(snapshot.change_pct) > 100
            ):
                snapshot = None
        except Exception:  # noqa: BLE001 - optional source fallback, no stale publication
            logger.warning("Yahoo stock daily bar unavailable for %s", symbol)
        if snapshot is None and key_id and secret:
            try:
                snapshot = _fetch_alpaca_sip_snapshot(symbol, report_date, key_id, secret)
                source = "Alpaca SIP"
                url = ALPACA_SOURCE_URL
            except Exception:  # noqa: BLE001 - omit unavailable optional quote
                logger.warning("Alpaca SIP stock daily bar unavailable for %s", symbol)
        if (
            snapshot is None
            or snapshot.day != report_date.isoformat()
            or not math.isfinite(snapshot.close)
            or snapshot.close <= 0
            or not math.isfinite(snapshot.change_pct)
            or abs(snapshot.change_pct) > 100
        ):
            missing.append(symbol)
            continue
        for field, metric, value, unit in (
            ("close", "stock_close", snapshot.close, "USD/share"),
            ("change_percent", "daily_return", snapshot.change_pct, "percent"),
        ):
            facts.append(
                MarketFact(
                    id=f"equity.{symbol.lower()}.{field}",
                    metric=metric,
                    instrument=symbol,
                    value=value,
                    previous=None,
                    change=snapshot.change_pct if field == "change_percent" else None,
                    unit=unit,
                    source=source,
                    source_url=url,
                    source_time=now,
                    retrieved_at=now,
                    quality="ok",
                    observation_date=report_date.isoformat(),
                )
            )
    return facts, tuple(missing)
