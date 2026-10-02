import pandas as pd
import pytest

from a_share_daily import data
from a_share_daily.charts.weekly_chart import generate_weekly_chart
from a_share_daily.data import get_week_dates


@pytest.fixture(autouse=True)
def calendar_root(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "_data_root", lambda: tmp_path)
    folder = tmp_path / "trade_cal"
    folder.mkdir()
    dates = pd.date_range("2026-08-25", "2026-08-31")
    pd.DataFrame(
        {
            "exchange": ["SSE"] * 7,
            "cal_date": dates.strftime("%Y%m%d"),
            "is_open": (dates.weekday < 5).astype(int),
        }
    ).to_parquet(folder / "a_share_trade_cal_latest.parquet")
    return folder / "a_share_trade_cal_latest.parquet"


def test_week_dates_skip_holiday_and_include_earlier_open_session(calendar_root):
    dates = [
        "20260923",
        "20260924",
        "20260925",
        "20260926",
        "20260927",
        "20260928",
        "20260929",
        "20260930",
    ]
    pd.DataFrame(
        {"exchange": ["SSE"] * 8, "cal_date": dates, "is_open": [1, 1, 0, 0, 0, 1, 1, 1]}
    ).to_parquet(calendar_root)
    assert get_week_dates("20260930") == [
        "20260923",
        "20260924",
        "20260928",
        "20260929",
        "20260930",
    ]


def test_week_dates_do_not_assume_weekdays_without_calendar(calendar_root):
    calendar_root.unlink()
    with pytest.raises(FileNotFoundError):
        get_week_dates("20260930")


@pytest.mark.parametrize("defect", ["short", "flag", "exchange", "gap"])
def test_week_dates_reject_untrusted_calendar_window(calendar_root, defect):
    frame = pd.read_parquet(calendar_root)
    if defect == "short":
        frame = frame.tail(2)
    elif defect == "flag":
        frame.loc[0, "is_open"] = 2
    elif defect == "exchange":
        frame = frame.drop(columns="exchange")
    else:
        frame = frame.loc[frame["cal_date"] != "20260829"]
    frame.to_parquet(calendar_root)
    with pytest.raises(ValueError):
        get_week_dates("20260831")


def test_week_dates_returns_trailing_week_through_trade_date() -> None:
    assert get_week_dates("20260831") == [
        "20260825",
        "20260826",
        "20260827",
        "20260828",
        "20260831",
    ]


def test_weekly_chart_accepts_trailing_week_for_monday(tmp_path) -> None:
    frame = pd.DataFrame({"pct_chg": [1.0, -1.0, 0.0], "amount": [10.0, 20.0, 30.0]})
    out = tmp_path / "weekly.png"
    assert generate_weekly_chart(
        dict.fromkeys(get_week_dates("20260831"), frame), "20260831", str(out)
    ) == str(out)
