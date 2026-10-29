"""Exchange-session context for descriptive overseas observations."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

SHANGHAI = ZoneInfo("Asia/Shanghai")


def local_time(value: datetime) -> datetime:
    """Legacy naive report timestamps are explicitly interpreted in Shanghai."""
    return value.replace(tzinfo=SHANGHAI) if value.tzinfo is None else value.astimezone(SHANGHAI)


def observation_cutoff(date_text: str, generated: datetime | None = None) -> datetime:
    """Freeze morning inputs at 08:45; earlier runs cannot see later inputs."""
    target = datetime.strptime(date_text.replace("-", ""), "%Y%m%d")
    cutoff = target.replace(hour=8, minute=45, tzinfo=SHANGHAI)
    return min(cutoff, local_time(generated)) if generated is not None else cutoff


def report_context(generated: datetime) -> dict[str, str]:
    local = local_time(generated)
    calendar = xcals.get_calendar("XSHG")
    day = local.date()
    if calendar.is_session(day):
        opening = calendar.session_open(day).to_pydatetime()
        closing = calendar.session_close(day).to_pydatetime()
        if local < opening:
            stage, next_session = "preopen", calendar.date_to_session(day)
        elif local < closing:
            stage, next_session = "intraday", calendar.date_to_session(day)
        else:
            stage, next_session = "postclose", calendar.next_session(day)
    else:
        stage, next_session = "closed", calendar.date_to_session(day, direction="next")
    return {
        "stage": stage,
        "next_session": next_session.date().isoformat(),
        "observed_at": local.isoformat(),
        "timezone": "Asia/Shanghai",
    }
