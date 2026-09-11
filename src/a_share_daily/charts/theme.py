"""Shared chart theme for A-share daily reports.

Two themes are provided:
  LIGHT - warm "graph-paper" light theme (the new default)
  DARK  - the original dark theme (kept available as a switchable option)

By default the module-level color constants (``BG``, ``FG``, ``UP``, ``DOWN``,
``FLAT``, ``PURPLE``, ``YELLOW``, ``BARS``, ``PANEL``, ``PANEL_ALT``,
``MUTED``, ``LINE``) resolve to the LIGHT theme, so existing chart generators
that ``from .theme import BG, FG, ...`` now render light automatically.

Call :func:`set_theme` to flip the whole process to another theme (e.g.
``set_theme(DARK)``), and :func:`apply_graph_paper` when a graph-paper sheet is
explicitly desired.  Report charts default to the quieter paper/card surface
used by Weekly Client Basket.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb, to_rgba
from matplotlib.image import BboxImage
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

from a_share_daily.data import cjk_font_path

_CJK = cjk_font_path()
_CJK_AVAILABLE = Path(_CJK).exists()
cjk = fm.FontProperties(fname=_CJK) if _CJK_AVAILABLE else None

# Heavy title font. Source Han Sans CN ships as clean single-face OTFs on the
# Linux host, which is more reliable for matplotlib than the multi-weight .ttc
# collections (and gives us a true bold/heavy weight for titles).
_CJK_HEAVY_CANDIDATES = (
    "/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Heavy.otf",
    "/usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Bold.otf",
    "C:/Windows/Fonts/SourceHanSansSC-Bold.otf",
    "C:/Windows/Fonts/NotoSansSC-Bold.ttf",
)
_CJK_HEAVY_PATH = next((p for p in _CJK_HEAVY_CANDIDATES if Path(p).exists()), None)
cjk_heavy = fm.FontProperties(fname=_CJK_HEAVY_PATH) if _CJK_HEAVY_PATH else cjk

# Display face for the large editorial headlines.  The reference report pairs a
# high-contrast Song/serif title with a quiet sans-serif information layer.
_CJK_DISPLAY_CANDIDATES = (
    "/usr/share/fonts/adobe-source-han-serif/SourceHanSerifCN-Heavy.otf",
    "/usr/share/fonts/adobe-source-han-serif/SourceHanSerifCN-Bold.otf",
    "C:/Windows/Fonts/SourceHanSerifSC-Heavy.otf",
    "C:/Windows/Fonts/NotoSerifSC-Black.ttf",
)
_CJK_DISPLAY_PATH = next((path for path in _CJK_DISPLAY_CANDIDATES if Path(path).exists()), None)
cjk_display = fm.FontProperties(fname=_CJK_DISPLAY_PATH) if _CJK_DISPLAY_PATH else cjk_heavy


@dataclass(frozen=True)
class ChartTheme:
    """Immutable description of a chart color scheme."""

    name: str
    BG: str
    WASH: str
    FG: str
    ACCENT: str
    UP: str
    DOWN: str
    FLAT: str
    PURPLE: str
    YELLOW: str
    BARS: tuple[str, ...]
    PANEL: str
    PANEL_ALT: str
    MUTED: str
    LINE: str
    GRID: str

    def rc(self) -> dict[str, Any]:
        return {
            "figure.facecolor": self.BG,
            "axes.facecolor": self.BG,
            "axes.edgecolor": self.LINE,
            "axes.labelcolor": self.FG,
            "text.color": self.FG,
            "xtick.color": self.MUTED,
            "ytick.color": self.FG,
            "grid.color": self.GRID,
            "grid.alpha": 0.5,
        }

    def apply(self, backend: Any = plt) -> None:
        backend.rcParams.update(self.rc())


DARK = ChartTheme(
    name="dark",
    BG="#1a1a2e",
    WASH="#22243b",
    FG="#e0e0e0",
    ACCENT="#6bc5ff",
    UP="#ff6b6b",
    DOWN="#00d4aa",
    FLAT="#555555",
    PURPLE="#7b68ee",
    YELLOW="#ffd93d",
    BARS=(
        "#00d4aa",
        "#7b68ee",
        "#ff6b6b",
        "#ffd93d",
        "#6bc5ff",
        "#ff922b",
        "#20c997",
        "#f06595",
        "#748ffc",
        "#ffe066",
    ),
    PANEL="#16213e",
    PANEL_ALT="#2a3150",
    MUTED="#8a91a8",
    LINE="#333333",
    GRID="#333333",
)

LIGHT = ChartTheme(
    name="light",
    BG="#f7f4ec",
    WASH="#edf0fa",
    FG="#111820",
    ACCENT="#b64d33",
    UP="#d64b45",
    DOWN="#2c8a64",
    FLAT="#a6adb6",
    PURPLE="#6551c8",
    YELLOW="#d99000",
    BARS=(
        "#b64d33",
        "#6551c8",
        "#d64b45",
        "#d99000",
        "#2c8a64",
        "#3f7cac",
        "#9b5de5",
        "#bc6c25",
        "#6b7c93",
        "#7a8b5a",
    ),
    PANEL="#f4f2eb",
    PANEL_ALT="#ebeae5",
    MUTED="#707985",
    LINE="#cdd0cf",
    GRID="#e2e1dc",
)

# Same-root editorial scale for ranked/composition visuals where category
# identity is already carried by direct labels.  Keeping this separate from
# ``BARS`` lets multi-category charts retain their semantic palette while the
# report-style surfaces stay close to the restrained blue/neutral reference.
BLUE_SCALE = (
    LIGHT.ACCENT,
    "#4778f2",
    "#7696ed",
    "#9eb2e6",
    "#becce3",
    "#d5deea",
    "#e6ebf1",
    "#f0f2f4",
)

# Default theme for all report charts.
DEFAULT_THEME = LIGHT

# Module-level color constants (what `from .theme import BG, ...` resolves to).
# Flipping these here flips every chart that imports them.
BG = DEFAULT_THEME.BG
WASH = DEFAULT_THEME.WASH
FG = DEFAULT_THEME.FG
ACCENT = DEFAULT_THEME.ACCENT
UP = DEFAULT_THEME.UP
DOWN = DEFAULT_THEME.DOWN
FLAT = DEFAULT_THEME.FLAT
PURPLE = DEFAULT_THEME.PURPLE
YELLOW = DEFAULT_THEME.YELLOW
BARS = DEFAULT_THEME.BARS
PANEL = DEFAULT_THEME.PANEL
PANEL_ALT = DEFAULT_THEME.PANEL_ALT
MUTED = DEFAULT_THEME.MUTED
LINE = DEFAULT_THEME.LINE
GRID = DEFAULT_THEME.GRID


def set_theme(theme: ChartTheme) -> None:
    """Switch the module-level color constants (and matplotlib rcParams) to ``theme``.

    Note: charts that did ``from .theme import BG`` at module load captured the
    color at import time, so this only affects code that reads the constants
    after the call (or re-imports). The LIGHT default already applies to all
    charts at import; use this to opt a specific render into the DARK theme.
    """
    global BG, WASH, FG, ACCENT, UP, DOWN, FLAT, PURPLE, YELLOW, BARS
    global PANEL, PANEL_ALT
    global MUTED, LINE, GRID
    BG = theme.BG
    WASH = theme.WASH
    FG = theme.FG
    ACCENT = theme.ACCENT
    UP = theme.UP
    DOWN = theme.DOWN
    FLAT = theme.FLAT
    PURPLE = theme.PURPLE
    YELLOW = theme.YELLOW
    BARS = theme.BARS
    PANEL = theme.PANEL
    PANEL_ALT = theme.PANEL_ALT
    MUTED = theme.MUTED
    LINE = theme.LINE
    GRID = theme.GRID
    theme.apply(plt)


def apply_editorial_background(
    fig: Any,
    theme: ChartTheme = LIGHT,
    *,
    graph_paper: bool = False,
) -> Any:
    """Paint the warm-to-cool editorial canvas without creating another axes.

    Avoiding a background axes keeps the public figure structure stable for
    chart tests and consumers that inspect ``figure.axes``.
    """
    if getattr(fig, "_a_share_editorial_background", False):
        return fig

    width = 512
    progress = np.clip((np.linspace(0, 1, width) - 0.42) / 0.58, 0, 1) ** 1.35
    warm = np.asarray(to_rgb(theme.BG))
    cool = np.asarray(to_rgb(theme.WASH))
    rgb = warm[None, :] * (1 - progress[:, None]) + cool[None, :] * progress[:, None]
    gradient = np.ones((2, width, 4), dtype=float)
    gradient[:, :, :3] = rgb[None, :, :]

    background = BboxImage(
        fig.bbox,
        origin="lower",
        interpolation="bicubic",
        zorder=-20,
    )
    background.set_data(gradient)
    fig.add_artist(background)
    fig.patch.set_facecolor(theme.BG)

    if graph_paper:
        for index, position in enumerate(np.arange(0, 1.0001, 0.05)):
            major = index % 2 == 0
            color = theme.LINE if major else theme.GRID
            alpha = 0.34 if major else 0.28
            linewidth = 0.50 if major else 0.30
            fig.add_artist(
                Line2D(
                    [position, position],
                    [0, 1],
                    transform=fig.transFigure,
                    color=color,
                    alpha=alpha,
                    linewidth=linewidth,
                    zorder=-10,
                )
            )
            fig.add_artist(
                Line2D(
                    [0, 1],
                    [position, position],
                    transform=fig.transFigure,
                    color=color,
                    alpha=alpha,
                    linewidth=linewidth,
                    zorder=-10,
                )
            )

    fig._a_share_editorial_background = True
    return fig


def apply_graph_paper(fig: Any, theme: ChartTheme = LIGHT) -> Any:
    """Backward-compatible name for the shared editorial background."""
    return apply_editorial_background(fig, theme, graph_paper=True)


def add_report_header(
    fig: Any,
    *,
    title: str,
    kicker: str,
    subtitle: str | None = None,
    theme: ChartTheme = LIGHT,
    title_size: float = 21,
) -> None:
    """Add the reference-style serif headline and thin editorial rule."""
    apply_editorial_background(fig, theme)
    fig.text(
        0.055,
        0.966,
        kicker,
        color=theme.ACCENT,
        fontsize=8.5,
        fontproperties=cjk_heavy,
        va="top",
    )
    fig.text(
        0.055,
        0.925,
        title,
        color=theme.FG,
        fontsize=title_size,
        fontproperties=cjk_display,
        va="top",
    )
    if subtitle:
        fig.text(
            0.055,
            0.865,
            subtitle,
            color=theme.MUTED,
            fontsize=8.5,
            fontproperties=cjk,
            va="top",
        )
    rule_y = 0.835 if subtitle else 0.855
    fig.add_artist(
        Line2D(
            [0.055, 0.955],
            [rule_y, rule_y],
            transform=fig.transFigure,
            color=theme.LINE,
            linewidth=0.8,
            zorder=10,
        )
    )


def style_plot_axes(
    ax: Any,
    *,
    grid_axis: str | None = "y",
    theme: ChartTheme = LIGHT,
    panel_alpha: float = 0.52,
) -> None:
    """Apply the quiet paper-card treatment used across report plots."""
    ax.set_facecolor(to_rgba(theme.PANEL, panel_alpha if panel_alpha < 1 else 1))
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(theme.LINE)
        spine.set_linewidth(0.65)
    ax.tick_params(colors=theme.MUTED, length=0)
    ax.grid(False)
    if grid_axis:
        ax.grid(
            axis=grid_axis,
            color=theme.LINE,
            alpha=0.58,
            linewidth=0.65,
        )


def add_card(
    ax: Any,
    *,
    theme: ChartTheme = LIGHT,
    rounding: float = 0.018,
    linewidth: float = 0.7,
) -> None:
    """Add a restrained rounded card behind an axes' content."""
    ax.set_facecolor("none")
    ax.add_patch(
        FancyBboxPatch(
            (0, 0),
            1,
            1,
            boxstyle=f"round,pad=0.008,rounding_size={rounding}",
            transform=ax.transAxes,
            facecolor=theme.PANEL,
            edgecolor=theme.LINE,
            linewidth=linewidth,
            zorder=-2,
            clip_on=False,
        )
    )


def save_unavailable_chart(
    *,
    title: str,
    trade_date: str,
    reason: str,
    out_path: str,
) -> str:
    """Write a Chinese placeholder chart when a panel has no current data."""
    fig = plt.figure(figsize=(10, 5.5))
    apply_editorial_background(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.axis("off")
    display_date = (
        f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        if len(trade_date) == 8 and trade_date.isdigit()
        else trade_date
    )
    ax.text(
        0.5,
        0.68,
        f"{title}（{display_date}）",
        ha="center",
        va="center",
        fontsize=20,
        color=FG,
        fontproperties=cjk_display,
    )
    ax.text(
        0.5,
        0.50,
        "本项数据暂缺",
        ha="center",
        va="center",
        fontsize=17,
        color=YELLOW,
        fontproperties=cjk,
    )
    ax.text(
        0.5,
        0.38,
        reason,
        ha="center",
        va="center",
        fontsize=12,
        color=MUTED,
        fontproperties=cjk,
        wrap=True,
    )
    ax.text(
        0.5,
        0.24,
        "为避免发送旧图，market-intel 已用本次运行生成的占位图替代。",
        ha="center",
        va="center",
        fontsize=11,
        color="#888888",
        fontproperties=cjk,
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=BG, edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


__all__ = [
    "ChartTheme",
    "DARK",
    "LIGHT",
    "DEFAULT_THEME",
    "BG",
    "WASH",
    "FG",
    "ACCENT",
    "UP",
    "DOWN",
    "FLAT",
    "PURPLE",
    "YELLOW",
    "BARS",
    "BLUE_SCALE",
    "PANEL",
    "PANEL_ALT",
    "MUTED",
    "LINE",
    "GRID",
    "cjk",
    "cjk_heavy",
    "cjk_display",
    "set_theme",
    "apply_editorial_background",
    "apply_graph_paper",
    "add_report_header",
    "style_plot_axes",
    "add_card",
    "save_unavailable_chart",
]
