"""Build an offline Asia calendar projection from SSE metadata and exchange calendars.

Run with the platform environment: uv run python project_tools/export_public_asia_calendar.py
"""

from __future__ import annotations

import json
from pathlib import Path

import exchange_calendars

CONFIGS = Path(__file__).resolve().parents[1] / "config" / "public_calendars"
EXCHANGES = {
    "HK": ("XHKG", "https://www.hkex.com.hk/Services/Trading/Securities/Overview/Trading-Hours"),
    "JP": ("XTKS", "https://www.jpx.co.jp/english/corporate/about-jpx/calendar/"),
    "KR": ("XKRX", "https://global.krx.co.kr/"),
}


def build_calendar(sse: dict) -> dict:
    """Retain authoritative SSE provenance and derive only foreign sessions offline."""
    start, end = sse["coverage_start"], sse["coverage_end"]
    days = dict(sse["days"])
    markets = {day: ["CN"] if opened else [] for day, opened in days.items()}
    for market, (name, _url) in EXCHANGES.items():
        calendar = exchange_calendars.get_calendar(name, start=start, end=end)
        for session in calendar.sessions:
            day = session.date().isoformat()
            days[day] = True
            markets[day].append(market)
    return {
        **sse,
        "schema_version": "public_asia_calendar.v1",
        "exchange": "Asia",
        "source": "TuShare trade_cal + exchange_calendars",
        "exchange_calendars_version": exchange_calendars.__version__,
        "exchange_sources": {
            market: {"calendar": name, "url": url} for market, (name, url) in EXCHANGES.items()
        },
        "days": days,
        "markets": markets,
    }


def main() -> None:
    sse = json.loads((CONFIGS / "a-share-calendar.json").read_text(encoding="utf-8"))
    (CONFIGS / "asia-calendar.json").write_text(
        json.dumps(build_calendar(sse), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
