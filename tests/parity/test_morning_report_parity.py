from datetime import datetime

from a_share_daily.morning_report import render_morning_report


def test_morning_report_keeps_date_and_required_sections() -> None:
    manifest = {
        "date": "20260908",
        "date_dash": "2026-09-08",
        "topic_summary": {"topic_count": 2, "skipped": False},
        "cross_market": {"us_stocks": {"SPY": {"close": 1, "pct_chg": 0.2}}},
    }

    report = render_morning_report(manifest, {}, generated_at=datetime(2026, 9, 9, 7, 0))

    assert report.startswith("# 亚洲市场盘前 / 美股市场盘后（2026-09-08）")
    for section in (
        "## 1. 隔夜要闻",
        "## 2. 美股隔夜回顾",
        "## 3. 亚洲市场速览",
        "## 4. 跨市场传导信号",
        "## 5. A股盘前热点预判",
        "## 6. 宏观环境",
        "## 7. 数据质量",
    ):
        assert section in report


def test_morning_report_marks_missing_optional_data_as_degraded() -> None:
    report = render_morning_report(
        {"date_dash": "2026-09-08", "cross_market": {}},
        {},
        generated_at=datetime(2026, 9, 9, 7, 0),
    )

    assert "[WARN] 未取得通过结构化校验的新闻条目" in report
    assert "[WARN] 缺少 SPY/QQQ/SMH 基准行情" in report
    assert "[WARN] 未取得 hot-sector manifest" in report
