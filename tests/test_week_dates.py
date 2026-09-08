import pandas as pd

from a_share_daily.charts.weekly_chart import generate_weekly_chart
from a_share_daily.data import get_week_dates


def test_week_dates_returns_trailing_week_through_trade_date() -> None:
    assert get_week_dates("20260831") == ["20260825", "20260826", "20260827", "20260828", "20260831"]


def test_weekly_chart_accepts_trailing_week_for_monday(tmp_path) -> None:
    frame = pd.DataFrame({"pct_chg": [1.0, -1.0, 0.0], "amount": [10.0, 20.0, 30.0]})
    out = tmp_path / "weekly.png"
    assert generate_weekly_chart(
        dict.fromkeys(get_week_dates("20260831"), frame), "20260831", str(out)
    ) == str(out)
