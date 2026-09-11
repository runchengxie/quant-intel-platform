from __future__ import annotations

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from a_share_daily import pipeline
from a_share_daily.charts.dashboard import (
    MARGIN_PANEL_LEFT,
    generate_dashboard,
    margin_label_offset,
)
from a_share_daily.charts.sentiment import generate_sentiment
from a_share_daily.charts.weekly_chart import (
    WEEKLY_LEGEND_ANCHOR,
    WEEKLY_LEGEND_LOC,
    generate_weekly_chart,
    turnover_label_offset,
)
from a_share_daily.d11_h5_shadow_render import _compact_change_text


def test_weekly_legend_is_anchored_above_the_plot() -> None:
    assert WEEKLY_LEGEND_ANCHOR == (1.0, 1.02)
    assert WEEKLY_LEGEND_LOC == "lower right"


def test_d11_change_text_wraps_long_rotation_lists() -> None:
    rendered = _compact_change_text(
        "新增",
        [{"name": name} for name in ["恒逸石化", "宁德时代", "湖南裕能", "中国移动", "招商银行"]],
    )

    assert rendered.startswith("新增：")
    assert "\n" in rendered
    assert all(len(line) <= 16 for line in rendered.splitlines())


def test_weekly_turnover_labels_move_below_top_points() -> None:
    values = [21454.0, 20519.0, 18203.0, 17802.0, 20510.0]

    assert turnover_label_offset(values, 0) == (0, -14, "top")
    assert turnover_label_offset(values, 2) == (0, 10, "bottom")


def test_dashboard_margin_panel_stays_clear_of_sentiment_panel() -> None:
    assert MARGIN_PANEL_LEFT >= 0.40
    assert margin_label_offset([13376.0, 13437.0, 13488.0, 13429.0, 13559.0], 4) == (
        0,
        -12,
        "top",
    )


def test_dashboard_renders_when_optional_margin_data_is_empty(tmp_path) -> None:
    output = tmp_path / "dashboard.png"
    daily = pd.DataFrame({"pct_chg": [1.0, 0.0, -1.0]})
    turnover = pd.DataFrame({"date": ["20260904"], "amount": [100.0]})
    margin = pd.DataFrame(columns=["date", "rzye"])

    result = generate_dashboard(
        daily,
        limit_up_count=1,
        max_board=1,
        margin_df=margin,
        turnover_df=turnover,
        trade_date="20260904",
        out_path=str(output),
    )

    assert result == str(output)
    assert output.is_file()


def test_latest_partition_dates_returns_empty_for_missing_optional_dataset(
    monkeypatch, tmp_path
) -> None:
    data_root = tmp_path / "assets" / "tushare" / "a_share"
    monkeypatch.setattr(pipeline.D, "DATA_ROOT", data_root)

    assert pipeline._latest_partition_dates("margin", as_of_date="20260908") == []


def test_weekly_chart_subtitle_and_breadth_use_report_language(tmp_path, monkeypatch) -> None:
    rendered_text: list[str] = []
    original_text = Axes.text
    original_figure_text = Figure.text
    original_set_title = Axes.set_title

    def capture_text(self, x, y, text, *args, **kwargs):
        rendered_text.append(str(text))
        return original_text(self, x, y, text, *args, **kwargs)

    def capture_figure_text(self, x, y, s, *args, **kwargs):
        rendered_text.append(str(s))
        return original_figure_text(self, x, y, s, *args, **kwargs)

    def capture_set_title(self, label, *args, **kwargs):
        rendered_text.append(str(label))
        return original_set_title(self, label, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", capture_text)
    monkeypatch.setattr(Figure, "text", capture_figure_text)
    monkeypatch.setattr(Axes, "set_title", capture_set_title)
    frames = {
        day: pd.DataFrame({"pct_chg": [1.0, -1.0, 0.5, 0.0], "amount": [2_000_000] * 4})
        for day in ["20260907", "20260908", "20260909", "20260910", "20260911"]
    }

    assert generate_weekly_chart(frames, "20260911", str(tmp_path / "weekly.png"))
    assert any("上涨日" in text and "/5" in text for text in rendered_text)
    assert "市场广度" in rendered_text
    assert "成交活跃度（相对周均）" in rendered_text


def test_sentiment_chart_uses_breadth_strip_and_metric_language(tmp_path, monkeypatch) -> None:
    rendered_text: list[str] = []
    original_text = Axes.text
    original_set_title = Axes.set_title

    def capture_text(self, x, y, text, *args, **kwargs):
        rendered_text.append(str(text))
        return original_text(self, x, y, text, *args, **kwargs)

    def capture_set_title(self, label, *args, **kwargs):
        rendered_text.append(str(label))
        return original_set_title(self, label, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", capture_text)
    monkeypatch.setattr(Axes, "set_title", capture_set_title)
    daily = pd.DataFrame({"pct_chg": [1.0, -1.0, 0.0, 0.5]})

    generate_sentiment(daily, 2, "20260911", str(tmp_path / "sentiment.png"))

    assert "市场广度" in rendered_text
    assert "市场速览" in rendered_text
    assert any("涨 50%" in text for text in rendered_text)


def test_dashboard_uses_breadth_strip_and_thin_margin_line(tmp_path, monkeypatch) -> None:
    rendered_text: list[str] = []
    original_text = Axes.text
    original_set_title = Axes.set_title

    def capture_text(self, x, y, text, *args, **kwargs):
        rendered_text.append(str(text))
        return original_text(self, x, y, text, *args, **kwargs)

    def capture_set_title(self, label, *args, **kwargs):
        rendered_text.append(str(label))
        return original_set_title(self, label, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", capture_text)
    monkeypatch.setattr(Axes, "set_title", capture_set_title)
    daily = pd.DataFrame({"pct_chg": [1.0, -1.0, 0.0, 0.5]})
    turnover = pd.DataFrame({"date": ["20260911"], "amount": [100.0]})
    margin = pd.DataFrame({"date": ["20260911"], "rzye": [100.0]})

    generate_dashboard(daily, 2, 3, margin, turnover, "20260911", str(tmp_path / "dashboard.png"))

    assert "市场广度" in rendered_text
    assert "涨 50%" in rendered_text
    assert "融资余额趋势" in rendered_text
