"""Weekly rendering uses source facts and preserves missingness and sample scope."""

from pathlib import Path

import pytest
from PIL import Image

from a_share_analysis.weekly_recap_image import render_weekly_recap
from a_share_analysis.weekly_visual_facts import parse_weekly_facts
from a_share_analysis.weekly_visual_panels import (
    history_panel,
    market_panel,
    methods_panel,
    observation_panel,
)

REPORT = """# 本周市场背景
本周 5 个交易日，3 天上涨、2 天下跌。日均上涨家数占比 40%，个股平均涨幅 -0.20%。
成交情况：周总成交额 7.00 万亿元，日均 1.40 万亿元。
资金动向：全周主力资金净流出 120 亿元。
涨停统计：全周涨停 250 只，日均涨停 50.0 只。
外盘黄金：本周从 4000 美元降至 3990 美元，周涨跌幅为 -0.3%，整体走弱。
# 市场风格周报
### 01 当前状态
中性，已持续 2 周。
### 03 历史参考
历史上，当前状态共出现 15 周，分布在 3 段连续时期。
- 后续 4 周：收益中位数 -1.0%，正收益比例 40%（12 周样本）
- 后续 13 周：收益中位数 +2.0%，正收益比例 65%（11 周样本）
### 不同计算方法
- 基础市净率倒数（截至 2026-10-16）：过去 12 周累计 -2.0%，高于约 23% 的历史样本。过去 52 周累计 +5.0%，当前回撤 -4.0%。
### 04 下周观察
- 当前方向不明显。
- 配置上可保持当前的价值风格比例，避免根据单周波动频繁调整。
## 大小盘因子（风格）
- 小盘拥挤度：0.400
- 大盘拥挤度：0.800。低于 0.10 时触发小盘高拥挤。
### 04 下周观察
- 观察相对强弱短均线是否跌破长均线。
- 观察近 20 日拥挤证据是否回落至 0.90 以下。
"""


def test_reads_published_values_dates_and_samples_without_research_recalculation():
    facts = parse_weekly_facts(REPORT)
    assert facts.market["flow"] == -120
    assert facts.market["turnover"] == 7.0
    assert facts.market["gold_return"] == -0.3
    assert facts.outcomes[0].median == -1.0
    assert facts.outcomes[1].samples == 11
    assert facts.methods[0].date == "2026-10-16"
    assert facts.methods[0].ret12 == -2.0
    assert facts.crowding == {"small": 0.4, "large": 0.8}
    assert facts.sample_note == "同状态 15 周 · 3 段连续时期"
    assert len(facts.observations) == 4


@pytest.mark.parametrize(
    "old,new,error",
    [
        ("3 天上涨", "6 天上涨", "day counts"),
        ("65%（11 周样本）", "105%（11 周样本）", "sample facts"),
        ("0.400", "1.100", "crowding"),
    ],
)
def test_rejects_inconsistent_quantitative_facts(old, new, error):
    with pytest.raises(ValueError, match=error):
        parse_weekly_facts(REPORT.replace(old, new))


def test_does_not_invent_missing_data():
    facts = parse_weekly_facts("### 04 下周观察\n- 观察趋势。")
    assert facts.market == {}
    assert facts.outcomes == ()
    assert facts.methods == ()
    assert facts.crowding == {}
    assert facts.observations == ("观察趋势。",)


def test_visual_panels_and_real_composer_preserve_cards(tmp_path: Path, monkeypatch):
    from matplotlib.font_manager import findfont

    font = findfont("DejaVu Sans")
    monkeypatch.setattr("a_share_analysis.weekly_recap_image.cjk_font_path", lambda: font)
    facts = parse_weekly_facts(REPORT)
    for render in (history_panel, market_panel, methods_panel, observation_panel):
        panel = render(facts, font)
        assert panel is not None and panel.width == 1200
    value, size, report = (tmp_path / name for name in ("value.png", "size.png", "report.md"))
    Image.new("RGB", (1200, 600), "red").save(value)
    Image.new("RGB", (1200, 400), "blue").save(size)
    report.write_text(REPORT)
    out = render_weekly_recap(
        report=report,
        value_card=value,
        size_card=size,
        date="20261016",
        out=tmp_path / "weekly.png",
    )
    with Image.open(out) as image:
        assert image.getpixel((20, 650)) == (255, 0, 0)
        assert image.getpixel((20, 1250)) == (0, 0, 255)
        assert image.height < 12000


def test_empty_groups_skip_charts_and_oversized_observation_fails():
    from matplotlib.font_manager import findfont

    from a_share_analysis.weekly_visual_facts import WeeklyFacts

    font = findfont("DejaVu Sans")
    for render in (history_panel, market_panel, methods_panel, observation_panel):
        assert render(WeeklyFacts(), font) is None
    with pytest.raises(ValueError, match="readable panel"):
        observation_panel(WeeklyFacts(observations=("X" * 300,)), font)
