from pathlib import Path

import pytest
from PIL import Image

from a_share_analysis.weekly_recap_image import render_weekly_recap, report_highlights


def test_highlights_keep_current_state_and_observation_without_historical_sections():
    text = (
        "## 价值因子\n数据状态：完整。\n### 01 当前状态\n当前向上。\n"
        "### 02 证据\n历史数据\n### 04 下周观察\n- 观察趋势。\n"
        "## 大小盘\n### 01 当前状态\n大盘占优。"
    )
    assert report_highlights(text) == ["数据状态：完整。", "当前向上。", "观察趋势。", "大盘占优。"]


def test_single_image_preserves_both_cards_and_rejects_empty_report(tmp_path: Path, monkeypatch):
    from matplotlib.font_manager import findfont

    monkeypatch.setattr(
        "a_share_analysis.weekly_recap_image.cjk_font_path", lambda: findfont("DejaVu Sans")
    )
    value = tmp_path / "value.png"
    size = tmp_path / "size.png"
    Image.new("RGB", (1200, 1500), "red").save(value)
    Image.new("RGB", (1200, 900), "blue").save(size)
    report = tmp_path / "report.md"
    report.write_text(
        "### 01 当前状态\n完整的状态\n### 04 下周观察\n- 观察趋势。", encoding="utf-8"
    )
    out = render_weekly_recap(
        report=report,
        value_card=value,
        size_card=size,
        date="20261016",
        out=tmp_path / "single.png",
    )
    with Image.open(out) as image:
        assert image.width == 1200
        assert image.getpixel((20, 180)) == (255, 0, 0)
        assert image.getpixel((20, 1680)) == (0, 0, 255)
    report.write_text("无有效章节", encoding="utf-8")
    with pytest.raises(ValueError, match="no current state"):
        render_weekly_recap(
            report=report, value_card=value, size_card=None, date="20261016", out=out
        )
