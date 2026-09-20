"""Small deterministic PNG renderer for report content."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from .model import ReportDocument
from .themes import ReportTheme


def _cjk_font() -> fm.FontProperties | None:
    for candidate in (
        "/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ):
        path = Path(candidate)
        if path.is_file():
            return fm.FontProperties(fname=str(path))
    return None


def render_png(document: ReportDocument, theme: ReportTheme, output_path: Path) -> Path:
    fig = plt.figure(figsize=(10, 7), dpi=150, facecolor=theme.tokens["surface"])
    axis = fig.add_axes((0, 0, 1, 1))
    axis.axis("off")
    axis.set_facecolor(theme.tokens["surface"])
    font = _cjk_font()
    common = {"fontproperties": font} if font else {}
    axis.text(
        0.055,
        0.92,
        document.report_type.upper(),
        color=theme.tokens["accent"],
        fontsize=9,
        **common,
    )
    axis.text(
        0.055,
        0.84,
        document.title,
        color=theme.tokens["ink"],
        fontsize=25,
        fontweight="bold",
        **common,
    )
    axis.text(0.055, 0.78, document.report_date, color=theme.tokens["muted"], fontsize=10, **common)
    y = 0.68
    for group in document.metrics:
        axis.text(
            0.055,
            y,
            group.title,
            color=theme.tokens["ink"],
            fontsize=13,
            fontweight="bold",
            **common,
        )
        y -= 0.055
        for metric in group.metrics:
            axis.text(
                0.075,
                y,
                f"{metric.label}  {metric.value}{metric.unit}",
                color=theme.tokens["ink"],
                fontsize=11,
                **common,
            )
            y -= 0.045
        y -= 0.02
    for section in document.sections:
        axis.text(
            0.055,
            y,
            section.title,
            color=theme.tokens["ink"],
            fontsize=13,
            fontweight="bold",
            **common,
        )
        y -= 0.06
        for position in section.positions:
            axis.text(
                0.075,
                y,
                f"{position.symbol}  {position.name} · {position.status}",
                color=theme.tokens["ink"],
                fontsize=10,
                **common,
            )
            y -= 0.04
    axis.plot([0.055, 0.945], [0.745, 0.745], color=theme.tokens["rule"], linewidth=0.8)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, facecolor=theme.tokens["surface"], bbox_inches="tight")
    plt.close(fig)
    return output


__all__ = ["render_png"]
