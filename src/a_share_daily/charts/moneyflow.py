"""Moneyflow chart for top inflow and outflow stocks."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .theme import (
    BG,
    DOWN,
    FG,
    MUTED,
    UP,
    add_card,
    add_report_header,
    cjk,
    cjk_heavy,
    style_plot_axes,
)

IN_COLOR, OUT_COLOR = UP, DOWN


def generate_moneyflow(
    moneyflow_df,
    trade_date: str,
    out_path: str = "out/a_share_daily/daily_moneyflow_chart.png",
) -> str:
    df = moneyflow_df.copy()
    df = df[df["net_amount"].abs() > 1_000]
    df_in = df.nlargest(8, "net_amount")
    df_out = df.nsmallest(5, "net_amount")

    display_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    fig = plt.figure(figsize=(10, 5.8), facecolor=BG)
    add_report_header(
        fig,
        title="个股资金流向",
        kicker=f"{display_date} · A股日报",
        subtitle="主力净流入与净流出分列观察",
    )

    # Inflow (left)
    ax1 = fig.add_axes((0.07, 0.10, 0.40, 0.68))
    in_names = [f"{r['name']}\n{r['ts_code'][:6]}" for _, r in df_in.iterrows()]
    in_vals = df_in["net_amount"].values / 1e4
    bars1 = ax1.barh(np.arange(len(in_names)), in_vals, height=0.65, color=IN_COLOR, alpha=0.85)
    ax1.set_yticks(np.arange(len(in_names)))
    ax1.set_yticklabels(in_names, fontproperties=cjk, fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlabel("净流入（亿元）", fontproperties=cjk, fontsize=10, color=MUTED)
    ax1.set_title(
        f"主力净流入 Top {len(df_in)}",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        pad=9,
        color=FG,
    )
    for bar, v in zip(bars1, in_vals, strict=False):
        ax1.text(
            bar.get_width() + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{v:.1f}亿",
            va="center",
            fontsize=8,
            color=MUTED,
            fontproperties=cjk,
        )
    ax1.set_xlim(0, in_vals.max() * 1.25)
    style_plot_axes(ax1, grid_axis="x")
    add_card(ax1)

    # Outflow (right)
    ax2 = fig.add_axes((0.55, 0.10, 0.40, 0.68))
    out_names = [f"{r['name']}\n{r['ts_code'][:6]}" for _, r in df_out.iterrows()]
    out_vals = df_out["net_amount"].values / 1e4
    bars2 = ax2.barh(np.arange(len(out_names)), out_vals, height=0.65, color=OUT_COLOR, alpha=0.85)
    ax2.set_yticks(np.arange(len(out_names)))
    ax2.set_yticklabels(out_names, fontproperties=cjk, fontsize=9)
    ax2.invert_yaxis()
    ax2.set_xlabel("净流出（亿元）", fontproperties=cjk, fontsize=10, color=MUTED)
    ax2.set_title(
        f"主力净流出 Top {len(df_out)}",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        pad=9,
        color=FG,
    )
    for bar, v in zip(bars2, out_vals, strict=False):
        ax2.text(
            bar.get_width() - 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{abs(v):.1f}亿",
            va="center",
            ha="right",
            fontsize=8,
            color=MUTED,
            fontproperties=cjk,
        )
    ax2.set_xlim(out_vals.min() * 1.25, 0)
    style_plot_axes(ax2, grid_axis="x")
    add_card(ax2)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=BG, edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return str(out_path)
