"""Chart-ready rows preserve the PNG charts' numeric conventions and dates."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd

from a_share_daily.charts.public_extract import extract_chart_points
from a_share_daily.cross_market import _fetch_us_stocks


def metadata(key: str, day: str = "2026-09-18") -> dict:
    return {
        f"{key}_observation_date": day,
        f"{key}_source_label": "测试数据",
        f"{key}_source_url": "https://example.test/source",
    }


def test_sentiment_uses_the_same_breadth_counts_as_png():
    inputs = {
        "daily": pd.DataFrame([{"pct_chg": 2.0}, {"pct_chg": -1.0}, {"pct_chg": 0.0}]),
        "limit_up_count": 2,
        **metadata("sentiment"),
    }
    points = extract_chart_points("sentiment", inputs, "2026-09-18")
    assert [(p["label"], p["value"]) for p in points[:3]] == [
        ("上涨家数", 1.0),
        ("下跌家数", 1.0),
        ("平盘家数", 1.0),
    ]
    assert next(p["value"] for p in points if p["label"] == "平均涨跌") == 1 / 3


def test_moneyflow_uses_png_top_n_threshold_and_actual_partition_date():
    inputs = {
        "moneyflow": pd.DataFrame(
            [
                {"name": "流入", "ts_code": "000001.SZ", "net_amount": 11_000},
                {"name": "流出", "ts_code": "000002.SZ", "net_amount": -21_000},
                {"name": "过滤", "ts_code": "000003.SZ", "net_amount": 500},
            ]
        ),
        **metadata("moneyflow", "2026-09-17"),
    }
    points = extract_chart_points("moneyflow", inputs, "2026-09-18")
    assert [(p["label"], p["value"]) for p in points] == [
        ("流入 000001", 1.1),
        ("流出 000002", -2.1),
    ]
    assert all(p["observation_date"] == "2026-09-17" for p in points)
    assert all(p["unit"] == "亿元" for p in points)


def test_topic_uses_display_weight_and_source_date():
    inputs = {
        "topic": {
            "source_date": "20260917",
            "signal_date": "20260918",
            "topics": [{"topic": "AI", "weight": 0.4}, {"topic": "robotics", "weight": 0.2}],
        },
        **metadata("topic"),
    }
    points = extract_chart_points("topic", inputs, "2026-09-18")
    assert [(p["label"], p["value"]) for p in points] == [("人工智能", 40.0), ("机器人", 20.0)]
    assert all(p["observation_date"] == "2026-09-17" for p in points)


def test_weekly_uses_each_trading_days_date_and_png_aggregate():
    inputs = {
        "week_daily": {
            "20260917": pd.DataFrame(
                [{"pct_chg": 1, "amount": 100_000}, {"pct_chg": -1, "amount": 100_000}]
            ),
            "20260918": pd.DataFrame(
                [{"pct_chg": 2, "amount": 200_000}, {"pct_chg": 3, "amount": 100_000}]
            ),
        },
        **metadata("weekly_chart"),
    }
    points = extract_chart_points("weekly_chart", inputs, "2026-09-18")
    assert [
        (p["label"], p["value"], p["observation_date"]) for p in points if p["unit"] == "亿"
    ] == [
        ("成交额 2026-09-17", 2.0, "2026-09-17"),
        ("成交额 2026-09-18", 3.0, "2026-09-18"),
    ]


def test_dashboard_retains_mixed_units_and_component_dates():
    inputs = {
        "daily": pd.DataFrame([{"pct_chg": 1.0}, {"pct_chg": -2.0}]),
        "limit_up_count": 1,
        "max_board": 3,
        "turnover": pd.DataFrame([{"date": "20260917", "amount": 2.0}]),
        "margin": pd.DataFrame([{"date": "20260916", "rzye": 900.0}]),
        **metadata("dashboard"),
    }
    points = extract_chart_points("dashboard", inputs, "2026-09-18")
    assert ("上涨家数", 1.0, "家") in [(p["label"], p["value"], p["unit"]) for p in points]
    assert ("融资余额 2026-09-16", 900.0, "亿") in [
        (p["label"], p["value"], p["unit"]) for p in points
    ]
    assert (
        next(p["observation_date"] for p in points if p["label"].startswith("融资余额"))
        == "2026-09-16"
    )


def test_dashboard_margin_rows_keep_their_own_source():
    inputs = {
        "daily": pd.DataFrame([{"pct_chg": 1.0}]),
        "limit_up_count": 1,
        "max_board": 1,
        "turnover": pd.DataFrame([{"date": "20260918", "amount": 2.0}]),
        "margin": pd.DataFrame([{"date": "20260916", "rzye": 900.0}]),
        "dashboard_margin_source_label": "两融数据",
        "dashboard_margin_source_url": "https://example.test/margin",
        **metadata("dashboard"),
    }
    points = extract_chart_points("dashboard", inputs, "2026-09-18")
    margin = next(point for point in points if point["label"].startswith("融资余额"))
    assert margin["source_url"] == "https://example.test/margin"


def test_unobserved_limit_counts_are_not_exported_as_zero():
    inputs = {
        "daily": pd.DataFrame({"pct_chg": [1.0, -1.0]}),
        "limit_up_count": 0,
        "limit_up_observed": False,
        **metadata("sentiment"),
    }
    labels = {p["label"] for p in extract_chart_points("sentiment", inputs, "2026-09-18")}
    assert "涨停家数" not in labels


def test_overnight_requires_each_symbols_actual_close_date():
    inputs = {
        "us_stocks": {
            "SPY": {
                "pct_chg": 1.2,
                "as_of_date": "2026-09-17",
                "source_url": "https://finance.yahoo.com/quote/SPY/history/",
            },
            "QQQ": {"pct_chg": -0.8},
        },
        **metadata("us_overnight"),
    }
    points = extract_chart_points("us_overnight", inputs, "2026-09-18")
    assert [(p["label"], p["value"], p["observation_date"]) for p in points] == [
        ("标普500", 1.2, "2026-09-17")
    ]
    assert points[0]["source_url"] == "https://finance.yahoo.com/quote/SPY/history/"


def test_live_us_snapshot_captures_yfinance_close_row_date(monkeypatch):
    dates = pd.to_datetime(["2026-09-16", "2026-09-17"])
    frame = pd.DataFrame({("Close", "SPY"): [100.0, 102.0]}, index=dates)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    monkeypatch.setitem(
        sys.modules, "yfinance", SimpleNamespace(download=lambda *args, **kwargs: frame)
    )
    quotes = _fetch_us_stocks()
    assert quotes["SPY"] == {
        "close": 102.0,
        "pct_chg": 2.0,
        "as_of_date": "2026-09-17",
        "source_url": "https://finance.yahoo.com/quote/SPY/history/",
    }
