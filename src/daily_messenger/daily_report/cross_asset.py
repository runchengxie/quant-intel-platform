"""Date-aligned cross-asset futures facts for the public US market daily report."""

from __future__ import annotations

from datetime import UTC, date, datetime
from urllib.parse import quote

from daily_messenger.etl.fetchers.quotes import fetch_yahoo_daily_snapshot

from .models import MarketFact

CONTRACTS = (
    ("BZ=F", "brent", "Brent Last Day Financial Futures", "USD/barrel"),
    ("GC=F", "gold", "COMEX Gold continuous futures", "USD/troy_ounce"),
    ("SI=F", "silver", "COMEX Silver continuous futures", "USD/troy_ounce"),
    ("BTC=F", "bitcoin", "CME Bitcoin continuous futures", "USD/bitcoin"),
)


def _source_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/"


def fetch_cross_asset_facts(report_date: date) -> tuple[list[MarketFact], tuple[str, ...]]:
    """Fetch each continuous future independently; omit failures and nonmatching dates."""
    facts: list[MarketFact] = []
    missing: list[str] = []
    for symbol, key, instrument, unit in CONTRACTS:
        try:
            snapshot = fetch_yahoo_daily_snapshot(symbol)
            if snapshot.day != report_date.isoformat():
                missing.append(symbol)
                continue
            retrieved = datetime.now(UTC)
            common = {
                "instrument": f"{instrument} ({symbol})",
                "source": "Yahoo Finance",
                "source_url": _source_url(symbol),
                "source_time": retrieved,
                "retrieved_at": retrieved,
                "quality": "ok",
                "observation_date": snapshot.day,
            }
            facts.extend(
                (
                    MarketFact(
                        id=f"cross_asset.{key}.close",
                        metric="commodity_close" if key != "bitcoin" else "crypto_futures_close",
                        value=snapshot.close,
                        previous=None,
                        change=None,
                        unit=unit,
                        **common,
                    ),
                    MarketFact(
                        id=f"cross_asset.{key}.change_percent",
                        metric="daily_return",
                        value=snapshot.change_pct,
                        previous=None,
                        change=snapshot.change_pct,
                        unit="percent",
                        **common,
                    ),
                )
            )
        except Exception:  # noqa: BLE001 - each market is an independent optional source
            missing.append(symbol)
    return facts, tuple(missing)
