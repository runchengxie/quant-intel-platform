"""Date parsing and window helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BJT = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date


def parse_yyyymmdd(raw: str) -> date:
    return datetime.strptime(raw, "%Y%m%d").date()


def format_yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def today_bjt() -> date:
    return datetime.now(tz=BJT).date()


def subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year - years)


def resolve_date_range(
    start_date: str | None,
    end_date: str | None,
    years: int | None,
    *,
    default_years: int,
) -> tuple[date, date]:
    resolved_end = parse_yyyymmdd(end_date) if end_date else today_bjt()
    if start_date:
        resolved_start = parse_yyyymmdd(start_date)
    else:
        years_to_use = years if years is not None else default_years
        resolved_start = subtract_years(resolved_end, years_to_use)
    if resolved_start > resolved_end:
        raise ValueError("start_date must be <= end_date")
    return resolved_start, resolved_end


def iter_day_ranges(start: date, end: date) -> list[DateWindow]:
    if start > end:
        return []
    windows: list[DateWindow] = []
    cursor = start
    while cursor <= end:
        windows.append(DateWindow(start=cursor, end=cursor))
        cursor += timedelta(days=1)
    return windows


def iter_week_ranges(start: date, end: date) -> list[DateWindow]:
    if start > end:
        return []
    windows: list[DateWindow] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=6), end)
        windows.append(DateWindow(start=cursor, end=window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def _month_end(value: date) -> date:
    next_month = (value.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def iter_month_ranges(start: date, end: date) -> list[DateWindow]:
    if start > end:
        return []
    windows: list[DateWindow] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        window_end = min(_month_end(cursor), end)
        window_start = max(cursor, start)
        windows.append(DateWindow(start=window_start, end=window_end))
        cursor = window_end + timedelta(days=1)
    return windows
