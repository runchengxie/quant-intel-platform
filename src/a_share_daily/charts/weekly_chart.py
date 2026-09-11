"""Weekly recap chart with breadth bars and turnover line."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .theme import (
    BG,
    DOWN,
    FG,
    FLAT,
    LINE,
    MUTED,
    UP,
    YELLOW,
    add_card,
    add_report_header,
    cjk,
    cjk_heavy,
    style_plot_axes,
)

WEEKLY_LEGEND_ANCHOR = (1.0, 1.02)
WEEKLY_LEGEND_LOC = "lower right"


def turnover_label_offset(values: list[float], index: int) -> tuple[int, int, str]:
    """Keep labels near the top of the turnover plot away from its title."""
    high = max(values)
    low = min(values)
    span = max(high - low, 1.0)
    if values[index] >= high - span * 0.08:
        return (0, -14, "top")
    return (0, 10, "bottom")


def _weekly_period(
    daily_df_by_date: dict[str, pd.DataFrame], trade_date: str
) -> tuple[date, date, list[str]]:
    ref_date = date(int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:]))
    week_dates = sorted(ds for ds in daily_df_by_date if ds <= trade_date)[-5:]
    period_start = (
        date(int(week_dates[0][:4]), int(week_dates[0][4:6]), int(week_dates[0][6:]))
        if week_dates
        else ref_date
    )
    return ref_date, period_start, week_dates


def _daily_stats(daily_df_by_date: dict[str, pd.DataFrame], week_dates: list[str]) -> pd.DataFrame:
    daily_stats = []
    for ds in week_dates:
        df = daily_df_by_date[ds]
        daily_stats.append(
            {
                "date": ds,
                "up": int((df["pct_chg"] > 0).sum()),
                "down": int((df["pct_chg"] < 0).sum()),
                "flat": int((df["pct_chg"] == 0).sum()),
                "amount": df["amount"].sum() / 1e5,
            }
        )
    return pd.DataFrame(daily_stats)


def _plot_breadth(ax: Any, stats_df: pd.DataFrame, x: np.ndarray, labels: list[str]) -> None:
    totals = stats_df["up"] + stats_df["down"] + stats_df["flat"]
    up_share = stats_df["up"] / totals * 100
    down_share = stats_df["down"] / totals * 100
    flat_share = stats_df["flat"] / totals * 100
    y = np.arange(len(stats_df))
    ax.barh(y, up_share, color=UP, alpha=0.9, label="上涨", height=0.52)
    ax.barh(y, down_share, left=up_share, color=DOWN, alpha=0.9, label="下跌", height=0.52)
    ax.barh(
        y, flat_share, left=up_share + down_share, color=FLAT, alpha=0.9, label="平盘", height=0.52
    )
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5, color=FG)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 50, 100])
    ax.set_xticklabels(["0%", "50%", "100%"], fontsize=8, color=MUTED)
    ax.set_title("市场广度", loc="left", fontproperties=cjk_heavy, fontsize=11.5, pad=8, color=FG)
    ax.legend(
        frameon=False,
        prop=cjk,
        fontsize=8.5,
        labelcolor=FG,
        loc=WEEKLY_LEGEND_LOC,
        bbox_to_anchor=WEEKLY_LEGEND_ANCHOR,
        ncol=3,
        borderaxespad=0,
    )
    for index, (up_value, down_value) in enumerate(zip(up_share, down_share, strict=True)):
        ax.text(
            up_value / 2,
            index,
            f"{up_value:.0f}%",
            ha="center",
            va="center",
            fontsize=8,
            color="white",
        )
        if down_value >= 12:
            ax.text(
                up_value + down_value / 2,
                index,
                f"{down_value:.0f}%",
                ha="center",
                va="center",
                fontsize=8,
                color="white",
            )
    ax.invert_yaxis()
    style_plot_axes(ax, grid_axis="x")
    add_card(ax)


def _plot_turnover(ax: Any, stats_df: pd.DataFrame, x: np.ndarray, labels: list[str]) -> None:
    mean_amount = float(stats_df["amount"].mean())
    deviation = (stats_df["amount"] / mean_amount - 1) * 100
    ax.plot(x, deviation, color=YELLOW, marker="o", linewidth=2, markersize=6)
    amounts = [float(value) for value in deviation]
    for i, amount in enumerate(amounts):
        x_offset, y_offset, va = turnover_label_offset(amounts, i)
        ax.annotate(
            f"{amount:+.0f}%",
            (i, amount),
            textcoords="offset points",
            xytext=(x_offset, y_offset),
            ha="center",
            va=va,
            fontsize=8,
            color=MUTED,
            fontproperties=cjk,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, color=FG)
    ax.set_ylabel("相对周均", fontproperties=cjk, fontsize=10, color=MUTED)
    ax.set_title(
        "成交活跃度（相对周均）",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        pad=8,
        color=FG,
    )
    ax.axhline(0, color=LINE, linewidth=0.8)
    style_plot_axes(ax, grid_axis="y")
    add_card(ax)


def generate_weekly_chart(
    daily_df_by_date: dict[str, pd.DataFrame],
    trade_date: str,
    out_path: str = "out/a_share_daily/daily_weekly_chart.png",
) -> str | None:
    """daily_df_by_date: {date_str: daily_parquet_df} for each weekday this week."""
    ref_date, period_start, week_dates = _weekly_period(daily_df_by_date, trade_date)
    if len(week_dates) < 2:
        return None

    stats_df = _daily_stats(daily_df_by_date, week_dates)
    x = np.arange(len(stats_df))
    date_labels = [d[4:6] + "/" + d[6:8] for d in stats_df["date"]]
    up_days = int((stats_df["up"] > stats_df["down"]).sum())
    summary = (
        f"{len(stats_df)} 个交易日 · 上涨日 {up_days}/{len(stats_df)} · "
        f"周均成交额 {stats_df['amount'].mean():.0f}亿"
    )

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(9, 6),
        height_ratios=[2, 1.15],
        facecolor=BG,
        gridspec_kw={
            "left": 0.09,
            "right": 0.95,
            "top": 0.76,
            "bottom": 0.10,
            "hspace": 0.45,
        },
    )
    add_report_header(
        fig,
        title="本周市场复盘",
        kicker=f"{period_start:%m/%d}–{ref_date:%m/%d} · A股周报",
        subtitle=summary,
    )
    _plot_breadth(ax1, stats_df, x, date_labels)
    _plot_turnover(ax2, stats_df, x, date_labels)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=BG, edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return str(out_path)
