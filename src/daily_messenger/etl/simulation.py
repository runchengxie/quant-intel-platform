"""Deterministic fallback data for ETL dry runs and outages."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from daily_messenger.etl.types import FetchStatus

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def simulate_market_snapshot(trading_day: str) -> tuple[dict[str, Any], FetchStatus]:
    # Deterministic pseudo data keyed by date to keep examples stable.
    seed = sum(ord(ch) for ch in trading_day)
    index_level = 4800 + seed % 50
    ai_sector_perf = 1.2 + (seed % 7) * 0.1
    defensive_sector_perf = 0.8 + (seed % 5) * 0.05
    hk_change = ((seed % 9) - 4) * 0.2
    mag7_change = ((seed % 11) - 5) * 0.3

    market = {
        "date": trading_day,
        "indices": [
            {
                "symbol": "SPX",
                "close": round(index_level, 2),
                "change_pct": round((seed % 5 - 2) * 0.3, 2),
            },
            {
                "symbol": "NDX",
                "close": round(index_level * 1.2, 2),
                "change_pct": round((seed % 3 - 1) * 0.4, 2),
            },
        ],
        "sectors": [
            {"name": "AI", "performance": round(ai_sector_perf, 2)},
            {"name": "Defensive", "performance": round(defensive_sector_perf, 2)},
        ],
        "hk_indices": [
            {
                "symbol": "HSI",
                "close": 18000 + seed % 200,
                "change_pct": round(hk_change, 2),
            },
        ],
        "themes": {
            "ai": {
                "performance": round(ai_sector_perf, 2),
                "change_pct": round((seed % 5 - 2) * 0.5, 2),
                "avg_pe": 32.5,
                "avg_ps": 7.5,
            },
            "magnificent7": {
                "change_pct": round(mag7_change, 2),
                "avg_pe": 30.0,
                "avg_ps": 6.2,
                "market_cap": 12_000_000_000_000,
            },
        },
    }
    status = FetchStatus(name="market", ok=True, message="示例行情生成完毕")
    return market, status


def simulate_btc_theme(trading_day: str) -> tuple[dict[str, Any], FetchStatus]:
    seed = (len(trading_day) * 37) % 11
    net_inflow = (seed - 5) * 12.5
    funding_rate = 0.01 + seed * 0.001
    basis = 0.02 - seed * 0.0015

    btc = {
        "date": trading_day,
        "etf_net_inflow_musd": round(net_inflow, 2),
        "funding_rate": round(funding_rate, 4),
        "futures_basis": round(basis, 4),
    }
    status = FetchStatus(name="btc", ok=True, message="BTC 主题示例数据已生成")
    return btc, status


def simulate_events(trading_day: str) -> tuple[list[dict[str, Any]], FetchStatus]:
    today = datetime.now(PACIFIC_TZ)
    events = [
        {
            "title": "FOMC 会议纪要发布",
            "date": trading_day,
            "impact": "high",
        },
        {
            "title": "大型科技财报",
            "date": (
                today.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)
            ).strftime("%Y-%m-%d"),
            "impact": "medium",
        },
    ]
    status = FetchStatus(name="events", ok=True, message="事件日历已生成")
    return events, status
