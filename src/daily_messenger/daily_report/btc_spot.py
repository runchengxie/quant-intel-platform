"""BTC/USD spot observations; never substitute these for CME BTC futures."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests

from daily_messenger.etl.config import resolve_api_key
from daily_messenger.etl.types import QuoteSnapshot

from .fmp_prices import fetch_fmp_daily_snapshot
from .models import MarketFact

NEW_YORK = ZoneInfo("America/New_York")
KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
KRAKEN_SOURCE_URL = "https://www.kraken.com/prices/bitcoin"
COINGECKO_CHART_URL = "https://pro-api.coingecko.com/api/v3/coins/bitcoin/market_chart/range"
COINGECKO_SOURCE_URL = "https://www.coingecko.com/en/api"
FMP_CRYPTO_URL = (
    "https://site.financialmodelingprep.com/developer/docs/stable/"
    "cryptocurrency-historical-price-eod-full"
)


def _cutoff_start(day: date) -> int:
    cutoff = datetime.combine(day, time(16), NEW_YORK)
    return int((cutoff - timedelta(hours=1)).timestamp())


def _cutoff_milliseconds(day: date) -> int:
    return int(datetime.combine(day, time(16), NEW_YORK).timestamp() * 1000)


def _parse_coingecko_closes(prices: list[object], wanted: set[int]) -> dict[int, float]:
    closes: dict[int, float] = {}
    for point in prices:
        if not isinstance(point, list) or not point or type(point[0]) is not int:
            continue
        timestamp = point[0]
        if timestamp not in wanted:
            continue
        if len(point) != 2:
            raise RuntimeError("CoinGecko cutoff price invalid")
        raw_close = point[1]
        if isinstance(raw_close, bool) or not isinstance(raw_close, (int, float)):
            raise RuntimeError("CoinGecko cutoff price invalid")
        close = float(raw_close)
        if not math.isfinite(close) or close <= 0 or timestamp in closes:
            raise RuntimeError("CoinGecko cutoff price invalid or duplicated")
        closes[timestamp] = close
    return closes


def fetch_coingecko_spot_snapshot(target_date: date, api_key: str) -> QuoteSnapshot:
    """Use the two hourly CoinGecko USD points ending at 16:00 New York time."""
    cutoff = datetime.combine(target_date, time(16), NEW_YORK)
    if datetime.now(NEW_YORK) < cutoff:
        raise RuntimeError("CoinGecko target cutoff is not complete")
    previous_cutoff = datetime.combine(target_date - timedelta(days=1), time(16), NEW_YORK)
    try:
        response = requests.get(
            COINGECKO_CHART_URL,
            params={
                "vs_currency": "usd",
                "from": int((previous_cutoff - timedelta(hours=1)).timestamp()),
                "to": int((cutoff + timedelta(hours=1)).timestamp()),
                "interval": "hourly",
            },
            headers={"x-cg-pro-api-key": api_key},
            timeout=12,
        )
    except requests.RequestException as exc:
        raise RuntimeError("CoinGecko request failed") from exc
    if response.status_code != 200:
        raise RuntimeError(f"CoinGecko HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("CoinGecko response is not JSON") from exc
    prices = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(prices, list):
        raise RuntimeError("CoinGecko prices unavailable")
    previous = _cutoff_milliseconds(target_date - timedelta(days=1))
    target = _cutoff_milliseconds(target_date)
    closes = _parse_coingecko_closes(prices, {previous, target})
    if previous not in closes:
        raise RuntimeError("CoinGecko previous cutoff unavailable")
    if target not in closes:
        raise RuntimeError("CoinGecko target cutoff unavailable")
    return QuoteSnapshot(
        target_date.isoformat(),
        closes[target],
        (closes[target] / closes[previous] - 1) * 100,
        "coingecko:bitcoin:16ET",
    )


def _parse_kraken_closes(bars: list[object], wanted: set[int]) -> dict[int, float]:
    closes: dict[int, float] = {}
    for bar in bars:
        if not isinstance(bar, list) or not bar or type(bar[0]) is not int:
            continue
        start = bar[0]
        if start not in wanted:
            continue
        if len(bar) < 5:
            raise RuntimeError("Kraken cutoff bar invalid")
        raw_close = bar[4]
        if not isinstance(raw_close, (str, int, float)) or isinstance(raw_close, bool):
            raise RuntimeError("Kraken cutoff bar invalid")
        try:
            close = float(raw_close)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Kraken cutoff bar invalid") from exc
        if not math.isfinite(close) or close <= 0 or start in closes:
            raise RuntimeError("Kraken cutoff bar invalid or duplicated")
        closes[start] = close
    return closes


def fetch_kraken_spot_snapshot(target_date: date) -> QuoteSnapshot:
    """Return two complete BTC/USD hourly closes at 16:00 New York cutoffs."""
    cutoff = datetime.combine(target_date, time(16), NEW_YORK)
    if datetime.now(NEW_YORK) < cutoff:
        raise RuntimeError("Kraken target cutoff is not complete")
    try:
        response = requests.get(
            KRAKEN_OHLC_URL, params={"pair": "XBTUSD", "interval": 60}, timeout=12
        )
    except requests.RequestException as exc:
        raise RuntimeError("Kraken request failed") from exc
    if response.status_code != 200:
        raise RuntimeError(f"Kraken HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Kraken response is not JSON") from exc
    if not isinstance(payload, dict) or payload.get("error") != []:
        raise RuntimeError("Kraken response has errors")
    result = payload.get("result")
    bars = result.get("XXBTZUSD") if isinstance(result, dict) else None
    if not isinstance(bars, list):
        raise RuntimeError("Kraken BTC/USD bars unavailable")
    # Kraken documents the final OHLC row as the current, uncommitted interval.
    # A delayed response may still end with the 15:00-16:00 ET row after 16:00.
    completed_bars = bars[:-1]
    wanted = {_cutoff_start(target_date - timedelta(days=1)), _cutoff_start(target_date)}
    closes = _parse_kraken_closes(completed_bars, wanted)
    target = _cutoff_start(target_date)
    previous = _cutoff_start(target_date - timedelta(days=1))
    if previous not in closes:
        raise RuntimeError("Kraken previous cutoff unavailable")
    if target not in closes:
        raise RuntimeError("Kraken target cutoff unavailable")
    return QuoteSnapshot(
        target_date.isoformat(),
        closes[target],
        (closes[target] / closes[previous] - 1) * 100,
        "kraken:XBTUSD:16ET",
    )


def fetch_btc_spot_facts(report_date: date) -> tuple[list[MarketFact], str]:
    """Publish licensed FMP EOD, then authorized 16:00 ET spot fallbacks."""
    fmp_key = resolve_api_key("financial_modeling_prep")
    snapshot = None
    if fmp_key:
        try:
            snapshot = fetch_fmp_daily_snapshot(
                "BTCUSD", target_date=report_date, api_key=fmp_key, completed_after=time(18, 15)
            )
        except Exception:  # noqa: BLE001 - independent optional source
            snapshot = None
    source = "Financial Modeling Prep"
    source_url = FMP_CRYPTO_URL
    instrument = "BTC/USD cryptocurrency EOD (FMP BTCUSD)"
    status = "ok"
    source_time = datetime.now(UTC)
    if snapshot is None or snapshot.day != report_date.isoformat():
        coingecko_key = resolve_api_key("coingecko")
        if coingecko_key:
            try:
                snapshot = fetch_coingecko_spot_snapshot(report_date, coingecko_key)
            except Exception:  # noqa: BLE001 - use next independent source
                snapshot = None
        else:
            snapshot = None
        if snapshot is not None and snapshot.day == report_date.isoformat():
            source = "Data provided by CoinGecko"
            source_url = COINGECKO_SOURCE_URL
            instrument = "BTC/USD spot at 16:00 ET (CoinGecko bitcoin/USD)"
            status = "coingecko_fallback"
        else:
            try:
                snapshot = fetch_kraken_spot_snapshot(report_date)
            except Exception:  # noqa: BLE001 - fail closed without a verified price
                return [], "all_spot_sources_unavailable"
            if snapshot.day != report_date.isoformat():
                return [], "all_spot_sources_unavailable"
            source = "Kraken"
            source_url = KRAKEN_SOURCE_URL
            instrument = "BTC/USD spot at 16:00 ET (Kraken XBT/USD)"
            status = "kraken_fallback"
        source_time = datetime.combine(report_date, time(16), NEW_YORK).astimezone(UTC)
    retrieved = datetime.now(UTC)
    common = {
        "instrument": instrument,
        "source": source,
        "source_url": source_url,
        "source_time": source_time,
        "retrieved_at": retrieved,
        "quality": "ok",
        "observation_date": snapshot.day,
    }
    return [
        MarketFact(
            id="cross_asset.bitcoin_spot.close",
            metric="crypto_spot_close",
            value=snapshot.close,
            previous=None,
            change=None,
            unit="USD/bitcoin",
            **common,
        ),
        MarketFact(
            id="cross_asset.bitcoin_spot.change_percent",
            metric="daily_return",
            value=snapshot.change_pct,
            previous=None,
            change=snapshot.change_pct,
            unit="percent",
            **common,
        ),
    ], status
