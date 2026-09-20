from __future__ import annotations

from pathlib import Path

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from a_share_daily.charts.us_overnight import generate


def test_us_overnight_groups_market_and_leaders_and_writes_summary(
    tmp_path: Path, monkeypatch
) -> None:
    rendered_text: list[str] = []
    original_text = Axes.text
    original_figure_text = Figure.text

    def capture_text(self, x, y, text, *args, **kwargs):
        rendered_text.append(str(text))
        return original_text(self, x, y, text, *args, **kwargs)

    def capture_figure_text(self, x, y, s, *args, **kwargs):
        rendered_text.append(str(s))
        return original_figure_text(self, x, y, s, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", capture_text)
    monkeypatch.setattr(Figure, "text", capture_figure_text)
    output = tmp_path / "us.png"
    generate(
        {
            "SPY": {"pct_chg": -0.6},
            "QQQ": {"pct_chg": -1.1},
            "SMH": {"pct_chg": -2.4},
            "AAPL": {"pct_chg": 3.6},
            "MSFT": {"pct_chg": 0.2},
        },
        "20260715",
        str(output),
    )

    assert output.is_file()
    assert "市场 / 行业" in rendered_text
    assert "科技龙头" in rendered_text
    assert any("半导体领跌" in text for text in rendered_text)
