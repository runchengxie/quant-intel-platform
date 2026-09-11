"""US overnight performance bar chart for Mag7 and ETFs."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from a_share_daily.charts.theme import (
    BG,
    DOWN,
    FG,
    LINE,
    MUTED,
    UP,
    add_report_header,
    cjk,
    cjk_heavy,
    style_plot_axes,
)

# Symbols in display order: ETFs first, then Mag7, then semis
SYMBOLS = [
    "SPY",
    "QQQ",
    "SMH",
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "NVDA",
    "TSLA",
    "AMD",
    "AVGO",
]
LABELS = [
    "标普500",
    "纳指100",
    "半导体ETF",
    "苹果",
    "微软",
    "谷歌",
    "亚马逊",
    "Meta",
    "英伟达",
    "特斯拉",
    "AMD",
    "博通",
]


def generate(us_stocks: dict, trade_date: str, output: str) -> str:
    """Generate overnight US stock bar chart.

    Args:
        us_stocks: dict of {symbol: {close, pct_chg}} from cross_market
        trade_date: YYYYMMDD
        output: output PNG path
    Returns: output path
    """
    names, pcts, kinds = [], [], []
    for index, (sym, label) in enumerate(zip(SYMBOLS, LABELS, strict=False)):
        if sym in us_stocks and "pct_chg" in us_stocks[sym]:
            names.append(label)
            pcts.append(us_stocks[sym]["pct_chg"])
            kinds.append("market" if index < 3 else "leader")

    if not names:
        raise ValueError("no US stock data")

    colors = [
        MUTED if kind == "market" else UP if p >= 0 else DOWN
        for p, kind in zip(pcts, kinds, strict=True)
    ]
    positions: list[float] = []
    for index, kind in enumerate(kinds):
        positions.append(float(index + (0.6 if kind == "leader" and index >= 3 else 0)))
    y = np.asarray(positions)

    fig, ax = plt.subplots(figsize=(8, 5), facecolor=BG)
    bars = ax.barh(y, pcts, height=0.6, color=colors, alpha=0.85)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontproperties=cjk, fontsize=10)
    ax.invert_yaxis()
    ax.axvline(0, color=LINE, linewidth=1)
    ax.set_xlabel("涨跌幅 (%)", fontproperties=cjk, fontsize=10, color=MUTED)
    us_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    benchmark = dict(zip(SYMBOLS[:3], pcts[:3], strict=False))
    leader_pairs = [
        (name, pct)
        for name, pct, kind in zip(names, pcts, kinds, strict=True)
        if kind == "leader"
    ]
    strongest = max(leader_pairs, key=lambda item: item[1], default=None)
    semiconductor = benchmark.get("SMH")
    summary_parts = ["美股市场偏弱" if sum(benchmark.values()) < 0 else "美股市场偏强"]
    if semiconductor is not None:
        summary_parts.append(f"半导体{'领跌' if semiconductor < 0 else '领涨'}")
    if strongest is not None:
        summary_parts.append(f"{strongest[0]}逆势 {strongest[1]:+.1f}%")
    add_report_header(
        fig,
        title="隔夜美股表现",
        kicker=f"{us_date} · A股晨报",
        subtitle=" · ".join(summary_parts),
    )
    ax.set_title(
        "截至美东收盘",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        pad=9,
        color=FG,
    )
    span = max(max(pcts) - min(pcts), 1.0)
    padding = max(span * 0.12, 0.35)
    ax.set_xlim(
        min(min(pcts) - padding, -0.6),
        max(max(pcts) + padding, 0.6),
    )
    fig.text(
        0.5,
        0.015,
        "注：日期为美国市场交易日/美东时间，北京时间次日盘前使用。",
        ha="center",
        va="bottom",
        fontproperties=cjk,
        fontsize=8,
        color=MUTED,
    )

    for bar, p in zip(bars, pcts, strict=False):
        x = bar.get_width()
        offset = max(span * 0.025, 0.08) * (1 if x >= 0 else -1)
        ha = "left" if x >= 0 else "right"
        ax.text(
            x + offset,
            bar.get_y() + bar.get_height() / 2,
            f"{p:+.1f}%",
            va="center",
            ha=ha,
            fontsize=9,
            color=MUTED,
        )

    if any(kind == "market" for kind in kinds):
        ax.text(
            ax.get_xlim()[0],
            1.7,
            "市场 / 行业",
            color=MUTED,
            fontsize=8.5,
            fontproperties=cjk,
            va="bottom",
        )
    if any(kind == "leader" for kind in kinds):
        first_leader = next(index for index, kind in enumerate(kinds) if kind == "leader")
        ax.text(
            ax.get_xlim()[0],
            positions[first_leader] - 0.45,
            "科技龙头",
            color=MUTED,
            fontsize=8.5,
            fontproperties=cjk,
            va="bottom",
        )

    style_plot_axes(ax, grid_axis="x")
    fig.subplots_adjust(left=0.16, right=0.94, top=0.78, bottom=0.13)
    fig.savefig(output, dpi=150, facecolor=BG, edgecolor="none")
    plt.close(fig)
    return output
