"""Comprehensive market dashboard. 2x2 grid.

Panels: 涨跌分布 donut | 5-day turnover | 情绪指标 | 融资余额趋势
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

from .theme import (
    BG,
    DOWN,
    FG,
    FLAT,
    LINE,
    MUTED,
    PANEL,
    PURPLE,
    UP,
    YELLOW,
    add_report_header,
    cjk,
    cjk_heavy,
    style_plot_axes,
)

MARGIN_PANEL_LEFT = 0.42
MARGIN_PANEL_WIDTH = 0.54


def margin_label_offset(values: list[float], index: int) -> tuple[int, int, str]:
    """Keep financing-balance labels readable near the plot boundary."""
    high = max(values)
    low = min(values)
    span = max(high - low, 1.0)
    if values[index] >= high - span * 0.08:
        return (0, -12, "top")
    return (0, 8, "bottom")


def _draw_up_down_donut(ax, up: int, down: int, flat: int) -> None:
    sizes = [up, down, flat]
    colors = [UP, DOWN, FLAT]
    wedges, _ = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.45, "edgecolor": BG, "linewidth": 2},
    )
    up_pct = up / (up + down + flat) * 100
    ax.text(
        0,
        0.05,
        f"{up_pct:.0f}%",
        ha="center",
        va="center",
        fontsize=18,
        color=UP,
        fontweight="bold",
    )
    ax.text(
        0,
        -0.22,
        "上涨占比",
        ha="center",
        va="center",
        fontsize=9,
        color=MUTED,
        fontproperties=cjk,
    )
    labels = [f"涨 {up}", f"跌 {down}", f"平 {flat}"]
    ax.legend(
        wedges,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=3,
        frameon=False,
        prop=cjk,
        fontsize=8,
        labelcolor=FG,
    )
    ax.set_title(
        "涨跌分布",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        color=FG,
        pad=8,
    )


def _draw_turnover_panel(ax, turnover_df: pd.DataFrame) -> None:
    x = np.arange(len(turnover_df))
    labels_5d = [d[4:6] + "/" + d[6:8] for d in turnover_df["date"]]
    ax.bar(x, turnover_df["amount"], color=YELLOW, alpha=0.7, width=0.5)
    mean5 = float(turnover_df["amount"].mean())
    ax.axhline(y=mean5, color=MUTED, linestyle="--", linewidth=1, alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels_5d, fontsize=9, color=FG)
    ax.set_ylabel("成交额（亿）", fontproperties=cjk, fontsize=9, color=MUTED)
    ax.set_title(
        "近5日成交额",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        color=FG,
        pad=8,
    )
    for i, amt in enumerate(turnover_df["amount"]):
        ax.text(i, amt + 2, f"{amt:.0f}", ha="center", fontsize=7, color=FLAT)


def _draw_sentiment_panel(
    ax,
    up: int,
    down: int,
    flat: int,
    avg_pct: float,
    limit_up_count: int,
    max_board: int,
) -> None:
    ax.axis("off")
    cards3 = [
        ("今日涨停", f"{limit_up_count} 只", UP),
        ("最高连板", f"{max_board}天{max_board}板" if max_board > 0 else "-", YELLOW),
        ("平均涨跌", f"{avg_pct:.2f}%", UP if avg_pct > 0 else DOWN),
    ]
    for i, (label, value, clr) in enumerate(cards3):
        y = 0.78 - i * 0.29
        rect = Rectangle(
            (0, y),
            1,
            0.24,
            facecolor=PANEL,
            edgecolor=LINE,
            linewidth=1,
            zorder=0,
            transform=ax.transAxes,
        )
        ax.add_patch(rect)
        ax.text(
            0.08,
            y + 0.14,
            label,
            transform=ax.transAxes,
            fontproperties=cjk,
            fontsize=9,
            color=MUTED,
            va="center",
        )
        ax.text(
            0.08,
            y + 0.04,
            value,
            transform=ax.transAxes,
            fontproperties=cjk,
            fontsize=14,
            color=clr,
            va="center",
            fontweight="bold",
        )
    ax.set_title(
        "情绪指标",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        color=FG,
        pad=5,
    )


def _draw_margin_panel(ax, margin_df: pd.DataFrame) -> None:
    mx = np.arange(len(margin_df))
    mlabels = [d[4:6] + "/" + d[6:8] for d in margin_df["date"]]
    ax.fill_between(mx, margin_df["rzye"], alpha=0.3, color=PURPLE)
    ax.plot(mx, margin_df["rzye"], color=PURPLE, marker="o", linewidth=2, markersize=5)
    values = [float(value) for value in margin_df["rzye"]]
    for i, value in enumerate(values):
        x_offset, y_offset, va = margin_label_offset(values, i)
        ax.annotate(
            f"{value:.0f}",
            (i, value),
            textcoords="offset points",
            xytext=(x_offset, y_offset),
            ha="center",
            va=va,
            fontsize=7,
            color=FLAT,
        )
    ax.set_xticks(mx)
    ax.set_xticklabels(mlabels, fontsize=9, color=FG)
    ax.set_ylabel("融资余额（亿）", fontproperties=cjk, fontsize=9, color=MUTED)
    ax.set_title(
        "融资余额趋势",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        color=FG,
        pad=8,
    )


def generate_dashboard(
    daily,
    limit_up_count: int,
    max_board: int,
    margin_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    trade_date: str,
    out_path: str = "out/a_share_daily/daily_dashboard.png",
) -> str:
    up = int((daily["pct_chg"] > 0).sum())
    down = int((daily["pct_chg"] < 0).sum())
    flat = int((daily["pct_chg"] == 0).sum())
    avg_pct = daily["pct_chg"].mean()

    display_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    fig = plt.figure(figsize=(9.5, 7), facecolor=BG)
    add_report_header(
        fig,
        title="综合盘面",
        kicker=f"{display_date} · A股日报",
        subtitle="市场广度、成交额、情绪与融资余额",
    )

    # ── Panel 1: 涨跌分布 donut ──
    ax1 = fig.add_axes((0.04, 0.48, 0.42, 0.30), facecolor="none")
    _draw_up_down_donut(ax1, up, down, flat)

    # ── Panel 2: 5-day turnover ──
    ax2 = fig.add_axes((0.52, 0.49, 0.44, 0.28))
    _draw_turnover_panel(ax2, turnover_df)
    style_plot_axes(ax2, grid_axis="y")

    # ── Panel 3: 情绪指标 ──
    ax3 = fig.add_axes((0.04, 0.08, 0.27, 0.32), facecolor="none")
    _draw_sentiment_panel(ax3, up, down, flat, avg_pct, limit_up_count, max_board)

    # ── Panel 4: 融资余额 ──
    ax4 = fig.add_axes((MARGIN_PANEL_LEFT, 0.10, MARGIN_PANEL_WIDTH, 0.29))
    _draw_margin_panel(ax4, margin_df)
    style_plot_axes(ax4, grid_axis="y")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=BG, edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return str(out_path)
