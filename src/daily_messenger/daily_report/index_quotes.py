"""Same-day US index close returns from completed Yahoo daily bars."""

from __future__ import annotations

from datetime import UTC, date, datetime
from urllib.parse import quote

from daily_messenger.etl.fetchers.quotes import fetch_yahoo_daily_snapshot

from .models import MarketFact

INDICES = (
    ("^GSPC", "spx", "S&P 500"),
    ("^DJI", "dow", "Dow Jones Industrial Average"),
    ("^IXIC", "nasdaq", "Nasdaq Composite"),
    ("^RUT", "russell2000", "Russell 2000"),
)


def fetch_index_facts(report_date: date) -> tuple[list[MarketFact], tuple[str, ...]]:
    """Return an atomic four-index close set or identify unavailable symbols."""
    snapshots = []
    missing = []
    for symbol, key, instrument in INDICES:
        try:
            snapshot = fetch_yahoo_daily_snapshot(symbol)
            if snapshot.day != report_date.isoformat():
                missing.append(symbol)
                continue
            snapshots.append((symbol, key, instrument, snapshot))
        except Exception:  # noqa: BLE001 - one unavailable source degrades the group
            missing.append(symbol)
    if missing:
        return [], tuple(missing)
    retrieved = datetime.now(UTC)
    facts = [
        MarketFact(
            id=f"index.{key}.change_percent",
            metric="daily_return",
            instrument=instrument,
            value=snapshot.change_pct,
            previous=None,
            change=snapshot.change_pct,
            unit="percent",
            source="Yahoo Finance",
            source_url=f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/history/",
            source_time=retrieved,
            retrieved_at=retrieved,
            quality="ok",
            observation_date=snapshot.day,
        )
        for symbol, key, instrument, snapshot in snapshots
    ]
    return facts, ()
