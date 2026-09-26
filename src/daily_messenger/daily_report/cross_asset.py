"""Date-aligned cross-asset futures facts for the public US market daily report."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from urllib.parse import quote

from daily_messenger.etl.config import resolve_api_key
from daily_messenger.etl.fetchers.quotes import fetch_yahoo_daily_snapshot

from .fmp_prices import fetch_fmp_daily_snapshot
from .models import MarketFact

CONTRACTS = (
    ("BZ=F", "brent", "Brent Last Day Financial Futures", "USD/barrel"),
    ("GC=F", "gold", "COMEX Gold continuous futures", "USD/troy_ounce"),
    ("SI=F", "silver", "COMEX Silver continuous futures", "USD/troy_ounce"),
    ("BTC=F", "bitcoin", "CME Bitcoin continuous futures", "USD/bitcoin"),
)

# Yahoo's currentTradingPeriod may extend to 23:59 ET even after these
# exchange sessions finish. These conservative cutoffs are for Yahoo daily
# bars, not a claim that Yahoo's close equals an exchange settlement price.
COMPLETED_AFTER = {"BZ=F": time(18, 15), "GC=F": time(17, 15), "SI=F": time(17, 15)}
FMP_COMMODITIES = {"BZ=F": "BZUSD", "GC=F": "GCUSD", "SI=F": "SIUSD"}
FMP_SOURCE_URL = "https://site.financialmodelingprep.com/developer/docs/stable/commodities-historical-price-eod-full"


def _source_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/"


def fetch_cross_asset_facts(report_date: date) -> tuple[list[MarketFact], dict[str, str]]:
    """Fetch each continuous future independently; omit failures and nonmatching dates."""
    facts: list[MarketFact] = []
    missing: dict[str, str] = {}
    fmp_key = resolve_api_key("financial_modeling_prep")
    for symbol, key, instrument, unit in CONTRACTS:
        try:
            source = "Yahoo Finance"
            source_url = _source_url(symbol)
            fact_instrument = f"{instrument} ({symbol})"
            try:
                snapshot = fetch_yahoo_daily_snapshot(
                    symbol, target_date=report_date, completed_after=COMPLETED_AFTER.get(symbol)
                )
            except Exception:
                if not fmp_key or symbol not in FMP_COMMODITIES:
                    raise
                snapshot = None
            if (snapshot is None or snapshot.day != report_date.isoformat()) and (
                fmp_key and symbol in FMP_COMMODITIES
            ):
                fmp_symbol = FMP_COMMODITIES[symbol]
                snapshot = fetch_fmp_daily_snapshot(
                    fmp_symbol,
                    target_date=report_date,
                    api_key=fmp_key,
                    completed_after=COMPLETED_AFTER.get(symbol),
                )
                source = "Financial Modeling Prep"
                source_url = FMP_SOURCE_URL
                fact_instrument = f"{instrument} (FMP {fmp_symbol}, continuous)"
            if snapshot is None:
                missing[symbol] = "provider_unavailable"
                continue
            if snapshot.day != report_date.isoformat():
                missing[symbol] = "observation_date_mismatch"
                continue
            retrieved = datetime.now(UTC)
            common = {
                "instrument": fact_instrument,
                "source": source,
                "source_url": source_url,
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
        except Exception as exc:  # noqa: BLE001 - each market is an independent optional source
            missing[symbol] = f"{type(exc).__name__}: {exc}"
    return facts, missing
