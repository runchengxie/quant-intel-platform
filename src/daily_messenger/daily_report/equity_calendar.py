"""Bounded XNYS equity sessions shared as a versioned package artifact."""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import cache
from importlib.resources import files
from typing import Any


@cache
def _calendar() -> dict[str, Any]:
    return json.loads(
        files("daily_messenger.daily_report").joinpath("data/equity_sessions_v1.json").read_text()
    )


def expected_observation_date(day: date) -> date:
    value = _calendar()["expected_observations"].get(day.isoformat())
    if value is None:
        raise ValueError("Equity calendar coverage unavailable")
    return date.fromisoformat(value)


def session_close(day: date) -> datetime:
    value = _calendar()["session_closes"].get(day.isoformat())
    if value is None:
        raise ValueError("Equity session close coverage unavailable")
    return datetime.fromisoformat(value)


def previous_session_date(day: date) -> date:
    session_close(day)
    preceding = [value for value in _calendar()["session_closes"] if value < day.isoformat()]
    if not preceding:
        raise ValueError("Previous equity session coverage unavailable")
    return date.fromisoformat(max(preceding))


def session_metadata(day: date) -> dict[str, str]:
    observed = expected_observation_date(day).isoformat()
    return {
        "session": "open" if observed == day.isoformat() else "closed",
        "expected_observation_date": observed,
        "observation_date": observed,
        "calendar_version": _calendar()["calendar_version"],
        "calendar_source": _calendar()["calendar_source"],
    }


def valid_reference(fact: dict[str, Any], report_date: str, status: dict[str, Any]) -> bool:
    """Independently verify closed-day metadata against the pinned calendar."""
    try:
        expected = session_metadata(date.fromisoformat(report_date))
    except (ValueError, TypeError):
        return False
    return (
        expected["session"] == "closed"
        and all(status.get(key) == value for key, value in expected.items())
        and status.get("reason") == "holiday_reference"
        and fact.get("observation_date") == expected["expected_observation_date"]
        and fact.get("quality") == "lagged"
    )
