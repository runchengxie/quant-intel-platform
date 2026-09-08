from datetime import date

from tushare_jobs.windowing import (
    iter_month_ranges,
    iter_week_ranges,
    resolve_date_range,
)


def test_iter_week_ranges():
    windows = iter_week_ranges(date(2024, 1, 1), date(2024, 1, 10))
    assert windows[0].start == date(2024, 1, 1)
    assert windows[0].end == date(2024, 1, 7)
    assert windows[1].start == date(2024, 1, 8)
    assert windows[1].end == date(2024, 1, 10)


def test_iter_month_ranges_mid_month():
    windows = iter_month_ranges(date(2024, 1, 15), date(2024, 3, 2))
    assert windows[0].start == date(2024, 1, 15)
    assert windows[0].end == date(2024, 1, 31)
    assert windows[1].start == date(2024, 2, 1)
    assert windows[1].end == date(2024, 2, 29)
    assert windows[2].start == date(2024, 3, 1)
    assert windows[2].end == date(2024, 3, 2)


def test_resolve_date_range_default_years():
    start, end = resolve_date_range(None, "20240115", 1, default_years=1)
    assert end == date(2024, 1, 15)
    assert start == date(2023, 1, 15)
