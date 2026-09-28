"""Date-aligned cross-asset futures facts for the public US market daily report."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from urllib.parse import quote

from daily_messenger.etl.fetchers.quotes import fetch_yahoo_daily_snapshot

from .models import MarketFact

CONTRACTS = (
    ("BZ=F", "brent", "Brent Last Day Financial Futures", "USD/barrel"),
    ("GC=F", "gold", "COMEX Gold futures", "USD/troy_ounce"),
    ("SI=F", "silver", "COMEX Silver futures", "USD/troy_ounce"),
    ("BTC=F", "bitcoin", "CME Bitcoin continuous futures", "USD/bitcoin"),
)

# Yahoo's currentTradingPeriod may extend to 23:59 ET even after these
# exchange sessions finish. These conservative cutoffs are for Yahoo daily
# bars, not a claim that Yahoo's close equals an exchange settlement price.
COMPLETED_AFTER = {"BZ=F": time(18, 15), "GC=F": time(17, 15), "SI=F": time(17, 15)}
MONTH_CODES = "FGHJKMNQUVXZ"
# Selected liquid benchmark months, not all listed months. CME added October
# to active GC months in 2026; December was the liquid benchmark in September.
DELIVERY_MONTHS = {"GC=F": (2, 4, 6, 8, 12), "SI=F": (3, 5, 7, 9, 12)}


def dated_contract_symbol(symbol: str, report_date: date) -> str:
    """Use a single delivery contract for both daily closes, never a rolled alias."""
    if symbol == "BZ=F":
        offset = 2  # Last-day financial Brent expires two calendar months ahead.
        root, exchange = "BZ", "NYM"
    elif symbol in DELIVERY_MONTHS:
        offset = next(
            step
            for step in range(1, 13)
            if (report_date.month - 1 + step) % 12 + 1 in DELIVERY_MONTHS[symbol]
        )
        root, exchange = symbol.split("=")[0], "CMX"
    else:
        return symbol
    absolute_month = report_date.month - 1 + offset
    month = absolute_month % 12 + 1
    year = report_date.year + absolute_month // 12
    return f"{root}{MONTH_CODES[month - 1]}{year % 100:02d}.{exchange}"


def _source_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/"


def fetch_cross_asset_facts(report_date: date) -> tuple[list[MarketFact], dict[str, str]]:
    """Fetch dated commodity contracts; omit failures and nonmatching dates."""
    facts: list[MarketFact] = []
    missing: dict[str, str] = {}
    for symbol, key, instrument, unit in CONTRACTS:
        try:
            quote_symbol = dated_contract_symbol(symbol, report_date)
            source = "Yahoo Finance"
            source_url = _source_url(quote_symbol)
            fact_instrument = f"{instrument} ({quote_symbol})"
            snapshot = fetch_yahoo_daily_snapshot(
                quote_symbol,
                target_date=report_date,
                completed_after=COMPLETED_AFTER.get(symbol),
            )
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
