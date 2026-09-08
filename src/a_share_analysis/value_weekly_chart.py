"""Mobile-first decision card for the industry-neutral Value weekly report."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Patch

from a_share_daily.charts.theme import (
    ACCENT,
    LIGHT,
    apply_editorial_background,
    cjk,
    cjk_display,
)

CJK = cjk
CANVAS = LIGHT.BG
CARD = (1.0, 1.0, 1.0, 0.68)
INK = LIGHT.FG
MUTED = LIGHT.MUTED
GRID = LIGHT.LINE
BLUE = ACCENT
BLUE_LIGHT = "#dce5ff"
GOLD = LIGHT.YELLOW
GOLD_LIGHT = "#fff0c9"
GREY_BAR = LIGHT.FLAT


def _set_text(ax: plt.Axes, x: float, y: float, text: str, **kwargs: Any) -> None:
    kwargs.setdefault("fontproperties", CJK)
    ax.text(x, y, text, **kwargs)


def _style_panel(ax: plt.Axes, title: str, subtitle: str) -> None:
    ax.set_facecolor(CARD)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold", fontproperties=CJK)
    _set_text(
        ax,
        1,
        1.02,
        subtitle,
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.5,
        color=MUTED,
    )


def _current_streak(df: pd.DataFrame) -> int:
    regime = df["regime"].iloc[-1]
    return int(df["regime"].iloc[::-1].eq(regime).cumprod().sum())


def _kpi_card(ax: plt.Axes, title: str, value: str, note: str, accent: str) -> None:
    ax.set_axis_off()
    box = FancyBboxPatch(
        (0, 0),
        1,
        1,
        boxstyle="round,pad=0.012,rounding_size=0.035",
        transform=ax.transAxes,
        facecolor=CARD,
        edgecolor="none",
    )
    ax.add_patch(box)
    ax.add_patch(
        FancyBboxPatch(
            (0.055, 0.16),
            0.025,
            0.68,
            boxstyle="round,pad=0,rounding_size=0.012",
            transform=ax.transAxes,
            facecolor=accent,
            edgecolor="none",
        )
    )
    _set_text(ax, 0.12, 0.75, title, fontsize=8, color=MUTED, va="center")
    _set_text(ax, 0.12, 0.47, value, fontsize=14, color=INK, fontweight="bold", va="center")
    _set_text(ax, 0.12, 0.20, note, fontsize=7.2, color=MUTED, va="center")


def _momentum_spans(ax: plt.Axes, recent: pd.DataFrame) -> None:
    mask = recent["regime"].eq("MOMENTUM")
    starts = mask & ~mask.shift(fill_value=False)
    ends = mask & ~mask.shift(-1, fill_value=False)
    for start, end in zip(recent.index[starts], recent.index[ends], strict=True):
        span_start = float(mdates.date2num(pd.Timestamp(start).to_pydatetime()))
        span_end = float(mdates.date2num(pd.Timestamp(end).to_pydatetime() + timedelta(days=7)))
        ax.axvspan(span_start, span_end, color=GOLD_LIGHT, alpha=0.65, linewidth=0)


def _plot_nav(
    ax: plt.Axes, recent: pd.DataFrame, cluster_recent: pd.DataFrame | None = None
) -> None:
    _style_panel(
        ax,
        "近 104 周价值多空净值",
        "蓝色＝基础 1/PB；金色＝价值簇复合；背景＝趋势延续区制",
    )
    normalized = recent["cum"] / recent["cum"].iloc[0] * 100
    _momentum_spans(ax, recent)
    ax.plot(recent.index, normalized, color=BLUE, linewidth=2.1)
    ax.scatter(recent.index[-1], normalized.iloc[-1], color=BLUE, s=24, zorder=3)
    ax.annotate(
        f"{normalized.iloc[-1]:.1f}",
        (recent.index[-1], normalized.iloc[-1]),
        xytext=(-5, -12),
        textcoords="offset points",
        ha="right",
        va="top",
        color=BLUE,
        fontsize=8,
        fontweight="bold",
    )
    if cluster_recent is not None and len(cluster_recent):
        cluster_norm = cluster_recent["cum"] / cluster_recent["cum"].iloc[0] * 100
        ax.plot(cluster_recent.index, cluster_norm, color=GOLD, linewidth=1.6, linestyle="--")
        ax.scatter(cluster_recent.index[-1], cluster_norm.iloc[-1], color=GOLD, s=22, zorder=3)
        ax.annotate(
            f"{cluster_norm.iloc[-1]:.1f}",
            (cluster_recent.index[-1], cluster_norm.iloc[-1]),
            xytext=(-5, 10),
            textcoords="offset points",
            ha="right",
            va="bottom",
            color=GOLD,
            fontsize=8,
            fontweight="bold",
        )
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", rotation=0)
    ax.set_ylabel("净值", color=MUTED, fontsize=8, fontproperties=CJK)


def _plot_signal(ax: plt.Axes, recent: pd.DataFrame) -> None:
    _style_panel(ax, "12 周滚动复利收益", "虚线＝趋势阈值 +5%；灰线＝0%")
    values = recent["ret_12w"] * 100
    ax.axhline(0, color=GREY_BAR, linewidth=1)
    ax.axhline(5, color=GOLD, linewidth=1.2, linestyle="--")
    ax.plot(recent.index, values, color=BLUE, linewidth=1.8)
    ax.fill_between(recent.index, 0, values, color=BLUE_LIGHT, alpha=0.55)
    ax.scatter(recent.index[-1], values.iloc[-1], color=GOLD, s=28, zorder=3)
    ax.annotate(
        f"{values.iloc[-1]:+.1f}%",
        (recent.index[-1], values.iloc[-1]),
        xytext=(-5, -12),
        textcoords="offset points",
        ha="right",
        va="top",
        color=GOLD,
        fontsize=8,
        fontweight="bold",
    )
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_ylabel("收益率（%）", color=MUTED, fontsize=8, fontproperties=CJK)


def _plot_forward(
    ax: plt.Axes,
    patterns: dict[str, dict],
    regime: str,
    cluster_patterns: dict[str, dict] | None = None,
) -> None:
    current = patterns[regime]
    baseline = patterns["ALL"]
    regime_label = "趋势延续" if regime == "MOMENTUM" else "中性"
    subtitle = (
        f"中位数与 25%–75% 区间；{current['count']} 个周观察 / "
        f"{current['episode_count']} 段连续区制"
    )
    _style_panel(ax, "前瞻收益分布", subtitle)

    labels = ["4 周", "13 周", "26 周", "52 周"]
    keys = ["4w", "13w", "26w", "52w"]
    x = np.arange(len(keys))
    width = 0.26

    def values(pattern: dict) -> tuple[np.ndarray, np.ndarray]:
        medians = np.array([pattern["fwd_returns"][key]["median"] for key in keys], dtype=float)
        q25 = np.array([pattern["fwd_returns"][key]["q25"] for key in keys], dtype=float)
        q75 = np.array([pattern["fwd_returns"][key]["q75"] for key in keys], dtype=float)
        errors = np.vstack((medians - q25, q75 - medians))
        return medians, errors

    cluster_current = cluster_patterns[regime] if cluster_patterns is not None else None
    current_medians, current_errors = values(current)
    cluster_medians, cluster_errors = (
        values(cluster_current) if cluster_current is not None else (None, None)
    )
    baseline_medians, baseline_errors = values(baseline)
    ax.axhline(0, color=GREY_BAR, linewidth=1)
    ax.bar(
        x - width,
        current_medians,
        width,
        yerr=current_errors,
        color=GOLD,
        alpha=0.92,
        capsize=2,
        error_kw={"ecolor": INK, "elinewidth": 0.8},
    )
    if cluster_current is not None:
        assert cluster_medians is not None
        assert cluster_errors is not None
        ax.bar(
            x,
            cluster_medians,
            width,
            yerr=cluster_errors,
            color=BLUE,
            alpha=0.85,
            capsize=2,
            error_kw={"ecolor": INK, "elinewidth": 0.8},
        )
    ax.bar(
        x + width,
        baseline_medians,
        width,
        yerr=baseline_errors,
        color=GREY_BAR,
        alpha=0.85,
        capsize=2,
        error_kw={"ecolor": MUTED, "elinewidth": 0.8},
    )
    for position, value in zip(x - width, current_medians, strict=True):
        ax.text(position, value, f"{value:+.1f}", ha="center", va="bottom", fontsize=7, color=INK)
    if cluster_current is not None:
        assert cluster_medians is not None
        for position, value in zip(x, cluster_medians, strict=True):
            ax.text(
                position, value, f"{value:+.1f}", ha="center", va="bottom", fontsize=7, color=BLUE
            )
    ax.set_xticks(x, labels, fontproperties=CJK)
    ax.set_ylabel("收益率（%）", color=MUTED, fontsize=8, fontproperties=CJK)
    handles = [
        Patch(facecolor=GOLD, label=f"{regime_label}·基础"),
        Patch(facecolor=GREY_BAR, label="全样本"),
    ]
    if cluster_current is not None:
        handles.insert(1, Patch(facecolor=BLUE, label=f"{regime_label}·价值簇"))
    ax.legend(handles=handles, frameon=False, loc="upper left", fontsize=7.5, prop=CJK)


def _add_header(
    fig: plt.Figure,
    grid: Any,
    *,
    as_of_date: date,
    expected_through: date | None,
) -> None:
    header = fig.add_subplot(grid[0:2, :])
    header.set_axis_off()
    _set_text(
        header,
        0,
        0.72,
        "价值因子周报｜行业中性化",
        fontsize=21.5,
        color=INK,
        fontproperties=cjk_display,
        va="center",
    )
    complete = expected_through is None or as_of_date >= expected_through
    freshness = (
        "数据完整" if complete else f"预览：目标 {expected_through:%m-%d}，实际 {as_of_date:%m-%d}"
    )
    _set_text(header, 0, 0.25, f"数据截至 {as_of_date:%Y-%m-%d}", fontsize=9, color=MUTED)
    _set_text(
        header,
        1,
        0.25,
        freshness,
        fontsize=9,
        color=BLUE if complete else GOLD,
        ha="right",
        fontweight="bold",
    )


def _add_kpis(
    fig: plt.Figure,
    grid: Any,
    *,
    last: pd.Series,
    regime: str,
    regime_label: str,
    streak: int,
    percentile: float,
) -> None:
    cards = (
        ("当前区制", regime_label, f"本轮第 {streak} 周", GOLD if regime == "MOMENTUM" else BLUE),
        (
            "12 周复利",
            f"{last['ret_12w'] * 100:+.1f}%",
            f"历史第 {percentile:.0f} 百分位",
            BLUE,
        ),
        (
            "当前回撤",
            f"{last['drawdown']:.1f}%",
            f"周频最大 {last['max_drawdown_full']:.1f}%",
            BLUE,
        ),
        ("12 周波动率", f"{last['vol_12w'] * 100:.1f}%", "年化口径", BLUE),
    )
    for index, (title, value, note, accent) in enumerate(cards):
        _kpi_card(
            fig.add_subplot(grid[2:4, index * 3 : (index + 1) * 3]), title, value, note, accent
        )


def generate_value_weekly_card(
    df: pd.DataFrame,
    patterns: dict[str, dict],
    *,
    as_of_date: date,
    expected_through: date | None,
    out_path: str | Path,
    cluster: dict | None = None,
) -> str:
    """Render a 1200×1500-ish portrait card for Feishu mobile viewing.

    ``cluster`` optionally carries the value-cluster composite series as
    ``{"df": <weekly features>, "patterns": <historical patterns>}`` so the NAV
    and forward-return panels can show the new methodology alongside the base
    1/PB series.
    """
    last = df.iloc[-1]
    regime = str(last["regime"])
    regime_label = "趋势延续" if regime == "MOMENTUM" else "中性"
    streak = _current_streak(df)
    percentile = float((df["ret_12w"] <= last["ret_12w"]).mean() * 100)
    recent = df.tail(104)
    cluster_recent = cluster["df"].tail(104) if cluster is not None else None
    cluster_patterns = cluster["patterns"] if cluster is not None else None

    fig = plt.figure(figsize=(8, 10), dpi=150, facecolor=CANVAS)
    apply_editorial_background(fig)
    grid = fig.add_gridspec(
        15,
        12,
        left=0.055,
        right=0.965,
        top=0.96,
        bottom=0.075,
        hspace=1.15,
        wspace=0.7,
    )

    _add_header(fig, grid, as_of_date=as_of_date, expected_through=expected_through)
    _add_kpis(
        fig,
        grid,
        last=last,
        regime=regime,
        regime_label=regime_label,
        streak=streak,
        percentile=percentile,
    )

    _plot_nav(fig.add_subplot(grid[4:8, :]), recent, cluster_recent=cluster_recent)
    _plot_signal(fig.add_subplot(grid[8:11, :]), recent)
    _plot_forward(fig.add_subplot(grid[11:15, :]), patterns, regime, cluster_patterns)

    footer_target = expected_through.strftime("%Y-%m-%d") if expected_through else "未指定"
    fig.text(
        0.055,
        0.026,
        f"实际截止 {as_of_date:%Y-%m-%d}｜目标截止 {footer_target}｜月度调仓等权多空｜未计交易成本、ST 与做空约束｜口径对照（含约束参考）见正文",
        ha="left",
        va="center",
        fontsize=7.2,
        color=MUTED,
        fontproperties=CJK,
    )
    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, facecolor=CANVAS, edgecolor="none")
    plt.close(fig)
    return str(destination)
