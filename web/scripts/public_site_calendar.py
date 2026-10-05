"""Validate the public Asia calendar projection consumed by the freshness monitor."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CHINA_TZ = ZoneInfo("Asia/Shanghai")
CALENDAR_PATH = Path(__file__).resolve().parents[1] / "configs" / "asia-calendar.json"


def load_calendar() -> dict:
    """Missing or unreadable metadata fails closed at evaluation time."""
    try:
        value = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _validate_foreign_sources(calendar: dict) -> None:
    if not calendar["exchange_calendars_version"].startswith("4."):
        raise ValueError("invalid foreign calendar provenance")
    sources = calendar["exchange_sources"]
    expected = {
        "HK": ("XHKG", "www.hkex.com.hk"),
        "JP": ("XTKS", "www.jpx.co.jp"),
        "KR": ("XKRX", "global.krx.co.kr"),
    }
    if set(sources) != set(expected):
        raise ValueError("missing foreign exchange references")
    for market, (name, domain) in expected.items():
        source = sources[market]
        if source["calendar"] != name or not source["url"].startswith(f"https://{domain}/"):
            raise ValueError("invalid foreign exchange reference")


def session_expectation(calendar: dict, now: datetime) -> tuple[str, bool, datetime]:
    """Return the last due Asia session, closure deferral, and its publication deadline."""
    if calendar["schema_version"] != "public_asia_calendar.v1" or calendar["exchange"] != "Asia":
        raise ValueError("invalid Asia calendar identity")
    if calendar["source"] != "TuShare trade_cal + exchange_calendars" or len(calendar["source_sha256"]) != 64:
        raise ValueError("missing calendar provenance")
    int(calendar["source_sha256"], 16)
    if not calendar["source_url"].startswith("https://www.sse.com.cn/"):
        raise ValueError("missing exchange reference")
    _validate_foreign_sources(calendar)
    generated = datetime.fromisoformat(calendar["generated_at"])
    if generated.tzinfo is None or generated > now:
        raise ValueError("invalid calendar timestamp")
    start = date.fromisoformat(calendar["coverage_start"])
    end = date.fromisoformat(calendar["coverage_end"])
    today = now.astimezone(CHINA_TZ).date()
    days = calendar["days"]
    expected_keys = {(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)}
    if not start <= today < end or set(days) != expected_keys:
        raise ValueError("calendar coverage missing or expired")
    if any(type(value) is not bool for value in days.values()):
        raise ValueError("invalid session flag")
    deadline = datetime.combine(today, time(22), tzinfo=CHINA_TZ)
    due = [
        day
        for day, opened in days.items()
        if opened and (day < today.isoformat() or (day == today.isoformat() and now >= deadline))
    ]
    if not due or not any(opened and day > today.isoformat() for day, opened in days.items()):
        raise ValueError("calendar lacks adjacent sessions")
    latest = max(due)
    latest_deadline = datetime.combine(date.fromisoformat(latest), time(22), tzinfo=CHINA_TZ)
    return latest, not days[today.isoformat()] or now < deadline, latest_deadline
