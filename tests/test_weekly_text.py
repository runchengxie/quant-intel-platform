from __future__ import annotations

import pandas as pd

from a_share_daily.charts.weekly_text import _format_turnover, generate_weekly_text


def test_turnover_switches_to_trillion_yuan_for_market_scale_values() -> None:
    assert _format_turnover(113_579.0) == "11.36 万亿元"
    assert _format_turnover(22_716.0) == "2.27 万亿元"


def test_weekly_text_uses_billion_yuan_and_chinese_gold_direction() -> None:
    week_daily = {
        "20260730": pd.DataFrame({"pct_chg": [1.0, -0.5], "amount": [100_000, 200_000]}),
        "20260731": pd.DataFrame({"pct_chg": [2.0, 0.5], "amount": [120_000, 220_000]}),
    }

    report = generate_weekly_text(
        week_daily,
        week_limits={"20260730": 3, "20260731": 5},
        week_moneyflow={"20260730": -10.0, "20260731": -13.0},
        week_margin={},
        trade_date="20260731",
        week_gold={"20260730": 4000.0, "20260731": 4040.0},
    )

    assert "主力资金净流出 23 亿元" in report
    assert "周总成交额" in report
    assert "亿元" in report
    assert "整体走强" in report
    assert "从 4000 美元升至 4040 美元" in report
    assert "7月30日至7月31日" in report
    assert report.startswith("## 本周复盘（7月30日至7月31日）")
    assert "<!--" not in report
    assert "$" not in report
    assert "→" not in report
    assert not any(mark in report for mark in ("“", "”", "；", "——", "(", ")"))
    assert "[OK]" not in report
    assert "[WARN]" not in report
