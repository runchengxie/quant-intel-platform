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
FMP_CRYPTO_URL = (
    "https://site.financialmodelingprep.com/developer/docs/stable/"
    "cryptocurrency-historical-price-eod-full"
)


def _cutoff_start(day: date) -> int:
    cutoff = datetime.combine(day, time(16), NEW_YORK)
    return int((cutoff - timedelta(hours=1)).timestamp())


def _parse_kraken_closes(bars: list[object], wanted: set[int]) -> dict[int, float]:
    closes: dict[int, float] = {}
    for bar in bars:
        if not isinstance(bar, list) or len(bar) < 5 or type(bar[0]) is not int:
            continue
        start = bar[0]
        if start not in wanted:
            continue
        raw_close = bar[4]
        if not isinstance(raw_close, (str, int, float)) or isinstance(raw_close, bool):
            continue
        try:
            close = float(raw_close)
        except (TypeError, ValueError):
            continue
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
    wanted = {_cutoff_start(target_date - timedelta(days=1)), _cutoff_start(target_date)}
    closes = _parse_kraken_closes(bars, wanted)
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
    """Publish only licensed FMP spot facts; Kraken remains a private fallback probe."""
    fmp_key = resolve_api_key("financial_modeling_prep")
    if not fmp_key:
        return [], "fmp_key_missing"
    try:
        snapshot = fetch_fmp_daily_snapshot(
            "BTCUSD", target_date=report_date, api_key=fmp_key, completed_after=time(18, 15)
        )
    except Exception:  # noqa: BLE001 - independent optional price source
        try:
            fetch_kraken_spot_snapshot(report_date)
        except Exception:  # noqa: BLE001 - no public candidate without permission
            return [], "fmp_and_kraken_unavailable"
        return [], "kraken_private_fallback_only"
    if snapshot.day != report_date.isoformat():
        return [], "fmp_observation_date_mismatch"
    retrieved = datetime.now(UTC)
    common = {
        "instrument": "BTC/USD cryptocurrency EOD (FMP BTCUSD)",
        "source": "Financial Modeling Prep",
        "source_url": FMP_CRYPTO_URL,
        "source_time": retrieved,
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
    ], "ok"
