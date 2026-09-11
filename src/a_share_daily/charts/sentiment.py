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
    ax = fig.add_axes((0.07, 0.42, 0.86, 0.18), facecolor="none")
    total = max(up + down + flat, 1)
    shares = [up / total * 100, down / total * 100, flat / total * 100]
    left = 0.0
    for share, color in zip(shares, [UP, DOWN, FLAT], strict=True):
        ax.barh([0], [share], left=left, color=color, height=0.42, alpha=0.9)
        left += share
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.set_xticks([0, 50, 100])
    ax.set_xticklabels(["0%", "50%", "100%"], fontsize=8, color=MUTED)
    ax.set_title("市场广度", loc="left", fontproperties=cjk_heavy, fontsize=11.5, color=FG, pad=5)
    for share, label, _color, start in zip(
        shares, ["涨", "跌", "平"], [UP, DOWN, FLAT], [0, shares[0], shares[0] + shares[1]], strict=True
    ):
        if share >= 10:
            ax.text(start + share / 2, 0, f"{label} {share:.0f}%", ha="center", va="center", color="white", fontsize=9, fontproperties=cjk)


def _draw_stat_cards(fig: Any, daily: Any, limit_up_count: int, avg_pct: float, total: int) -> None:
    ax = fig.add_axes((0.07, 0.10, 0.86, 0.22), facecolor="none")
    ax.axis("off")
    cards = [
        ("涨停", f"{limit_up_count} 只", f"{limit_up_count / total * 100:.1f}%", UP),
        ("跌停", f"约 {_down_limit(daily)} 家", "", DOWN),
        ("个股总数", f"{total}", "", FLAT),
        ("平均涨跌", f"{avg_pct:.2f}%", "", DOWN if avg_pct < 0 else UP),
    ]
    for index, (label, value, sub, color) in enumerate(cards):
        x = index * 0.25
        rect = Rectangle(
            (x, 0.10),
            0.22,
            0.70,
            facecolor=PANEL,
            edgecolor=LINE,
            linewidth=1,
            zorder=0,
            transform=ax.transAxes,
        )
        ax.add_patch(rect)
        ax.text(
            x + 0.04,
            0.57,
            label,
            transform=ax.transAxes,
            fontproperties=cjk,
            fontsize=10,
            color=MUTED,
            va="center",
        )
        ax.text(
            x + 0.04,
            0.31,
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
                x + 0.04,
                0.14,
                sub,
                transform=ax.transAxes,
                fontproperties=cjk,
                fontsize=10,
                color=MUTED,
                va="center",
            )
    ax.text(0.0, 0.98, "市场速览", transform=ax.transAxes, fontproperties=cjk_heavy, fontsize=11.5, color=FG, va="top")


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
