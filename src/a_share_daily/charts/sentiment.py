"""Sentiment chart with donut and stat cards."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from .theme import (
    BG,
    DOWN,
    FG,
    FLAT,
    LINE,
    MUTED,
    PANEL,
    UP,
    add_report_header,
    cjk,
    cjk_heavy,
)


def _sentiment_stats(daily: Any) -> tuple[int, int, int, float, int]:
    up = int((daily["pct_chg"] > 0).sum())
    down = int((daily["pct_chg"] < 0).sum())
    flat = int((daily["pct_chg"] == 0).sum())
    avg_pct = daily["pct_chg"].mean()
    total = len(daily)
    return up, down, flat, avg_pct, total


def _draw_distribution(fig: Any, up: int, down: int, flat: int) -> None:
    ax = fig.add_axes((0.04, 0.09, 0.34, 0.68), facecolor="none")
    sizes = [up, down, flat]
    wedges, _ = ax.pie(
        sizes,
        labels=None,
        colors=[UP, DOWN, FLAT],
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.45, "edgecolor": BG, "linewidth": 2},
    )
    ax.text(
        0,
        0,
        f"{up}\n↑",
        ha="center",
        va="center",
        fontsize=14,
        color=UP,
        fontproperties=cjk,
        fontweight="bold",
    )
    legend_labels = [
        f"{label} {size}" for label, size in zip(["上涨", "下跌", "平盘"], sizes, strict=False)
    ]
    ax.legend(
        wedges,
        legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=3,
        frameon=False,
        prop=cjk,
        fontsize=9,
        labelcolor=FG,
    )
    ax.set_title("涨跌分布", loc="left", fontproperties=cjk_heavy, fontsize=11.5, color=FG, pad=5)


def _draw_stat_cards(fig: Any, daily: Any, limit_up_count: int, avg_pct: float, total: int) -> None:
    ax = fig.add_axes((0.43, 0.09, 0.52, 0.68), facecolor="none")
    ax.axis("off")
    cards = [
        ("涨停", f"{limit_up_count} 只", f"{limit_up_count / total * 100:.1f}%", UP),
        ("跌停", f"约 {_down_limit(daily)} 家", "", DOWN),
        ("个股总数", f"{total}", "", FLAT),
        ("平均涨跌", f"{avg_pct:.2f}%", "", DOWN if avg_pct < 0 else UP),
    ]
    for index, (label, value, sub, color) in enumerate(cards):
        y = 0.84 - index * 0.235
        rect = Rectangle(
            (0.05, y - 0.09),
            0.9,
            0.19,
            facecolor=PANEL,
            edgecolor=LINE,
            linewidth=1,
            zorder=0,
            transform=ax.transAxes,
        )
        ax.add_patch(rect)
        ax.text(
            0.12,
            y + 0.035,
            label,
            transform=ax.transAxes,
            fontproperties=cjk,
            fontsize=10,
            color=MUTED,
            va="center",
        )
        ax.text(
            0.12,
            y - 0.04,
            value,
            transform=ax.transAxes,
            fontproperties=cjk,
            fontsize=16,
            color=color,
            va="center",
            fontweight="bold",
        )
        if sub:
            ax.text(
                0.65,
                y - 0.04,
                sub,
                transform=ax.transAxes,
                fontproperties=cjk,
                fontsize=10,
                color=MUTED,
                va="center",
            )
    ax.set_title("市场速览", loc="left", fontproperties=cjk_heavy, fontsize=11.5, color=FG, pad=5)


def generate_sentiment(
    daily,
    limit_up_count: int,
    trade_date: str,
    out_path: str = "out/a_share_daily/daily_sentiment_chart.png",
) -> str:
    up, down, flat, avg_pct, total = _sentiment_stats(daily)

    display_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    fig = plt.figure(figsize=(9, 5), facecolor=BG)
    add_report_header(
        fig,
        title="市场情绪",
        kicker=f"{display_date} · A股日报",
        subtitle="涨跌分布与关键情绪指标",
    )

    _draw_distribution(fig, up, down, flat)
    _draw_stat_cards(fig, daily, limit_up_count, avg_pct, total)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=BG, edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


def _down_limit(daily) -> int:
    """Approximate 跌停 count."""
    total = 0
    for _, r in daily.iterrows():
        code = str(r.get("ts_code", ""))
        pct = float(r["pct_chg"])
        if code.startswith("300") or code.startswith("301") or code.startswith("688"):
            if pct <= -19.5:
                total += 1
        elif pct <= -9.5:
            total += 1
    return total
