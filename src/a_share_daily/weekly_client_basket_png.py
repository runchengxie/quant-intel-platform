"""Render a compact editorial PNG for the weekly basket."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .report_theme import ReportTheme, get_report_theme
from .weekly_client_basket import BasketArtifact
from .weekly_client_basket_render import SLEEVE_LABELS, STATUS_LABELS


def _render_header(ax, artifact: BasketArtifact, theme: ReportTheme) -> None:
    ax.set_facecolor(theme.surface)
    ax.axis("off")
    ax.text(0.02, 0.93, "周度组合 10", fontsize=27, fontweight="bold", color=theme.ink)
    ax.text(
        0.02, 0.82, "WEEKLY CLIENT BASKET  ·  "
        f"{artifact.report_date[:4]}-{artifact.report_date[4:6]}-{artifact.report_date[6:]}",
        fontsize=10, color=theme.muted,
    )
    ax.text(0.02, 0.69, "三策略混合 · 周内默认冻结 · 研究观察用途", fontsize=12, color=theme.ink)
    stats = (
        ("股票", len(artifact.positions)),
        ("日内观察", sum(p.source_strategy == "dailywatch_family" for p in artifact.positions)),
        ("现金流因子", sum(p.source_strategy == "cashflow" for p in artifact.positions)),
        ("微盘股", sum(p.source_strategy == "microcap" for p in artifact.positions)),
    )
    for index, (label, value) in enumerate(stats):
        x = 0.02 + index * 0.245
        ax.text(x, 0.42, str(value), fontsize=23, fontweight="bold", color=theme.accent)
        ax.text(x, 0.31, label, fontsize=9, color=theme.muted)
    ax.plot([0.02, 0.98], [0.22, 0.22], color=theme.rule, linewidth=0.8)
    ax.text(0.02, 0.10, "本周组合", fontsize=13, fontweight="bold", color=theme.ink)


def _render_card(card, index: int, position, theme: ReportTheme, fancy_box) -> None:
    card.set_facecolor(theme.panel)
    card.axis("off")
    card.add_patch(
        fancy_box(
            (0, 0), 1, 1, boxstyle="round,pad=0.012,rounding_size=0.015",
            linewidth=0.7, edgecolor=theme.rule, facecolor=theme.panel,
            transform=card.transAxes,
        )
    )
    card.text(0.05, 0.78, f"{index + 1:02d}", fontsize=11, color=theme.accent)
    card.text(
        0.17, 0.78, position.name or "未命名", fontsize=12,
        fontweight="bold", color=theme.ink,
    )
    card.text(0.17, 0.55, position.symbol, fontsize=9, color=theme.muted)
    card.text(
        0.05, 0.18, SLEEVE_LABELS.get(position.source_strategy, position.source_strategy),
        fontsize=8, color=theme.muted,
    )
    card.text(
        0.90, 0.18, STATUS_LABELS.get(position.status, position.status), fontsize=8,
        ha="right", color=theme.accent,
    )


def _render_curve(curve_ax, performance: Mapping[str, object] | None, theme: ReportTheme) -> None:
    curve_ax.set_facecolor(theme.panel)
    raw_series = (performance or {}).get("series", [])
    series: list[Mapping[str, Any]] = []
    if isinstance(raw_series, list):
        series = [
            cast(Mapping[str, Any], row)
            for row in raw_series
            if isinstance(row, Mapping) and isinstance(row.get("nav"), (int, float))
        ]
    if series:
        values = [float(row["nav"]) for row in series]
        curve_ax.plot(range(len(values)), values, color=theme.accent, linewidth=2.2)
        curve_ax.fill_between(
            range(len(values)), values, min(values), color=theme.accent, alpha=0.08
        )
        curve_ax.set_title(
            "历史净值 · provider performance.json", loc="left", color=theme.ink, fontsize=11
        )
        curve_ax.text(
            1.0, 1.04, f"{values[-1] / values[0] - 1:+.2%}",
            transform=curve_ax.transAxes, ha="right", color=theme.accent,
        )
    else:
        curve_ax.text(
            0.02, 0.5, "历史净值：等待 provider performance.json",
            color=theme.muted, transform=curve_ax.transAxes,
        )
    curve_ax.tick_params(colors=theme.muted, labelsize=7)
    for spine in curve_ax.spines.values():
        spine.set_color(theme.rule)
    curve_ax.grid(axis="y", color=theme.rule, alpha=0.5, linewidth=0.5)


def render_basket_png(
    artifact: BasketArtifact,
    output_path: str | Path,
    *,
    theme: str | ReportTheme = "research_editorial",
    performance: Mapping[str, object] | None = None,
) -> Path:
    """Render the same content model as Markdown into a Feishu-friendly image."""
    selected = get_report_theme(theme) if isinstance(theme, str) else theme
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    plt.rcParams["font.sans-serif"] = ["Source Han Sans CN", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    output = Path(output_path).expanduser().resolve()
    fig = plt.figure(figsize=(12.0, 13.5), dpi=140, facecolor=selected.surface)
    grid = fig.add_gridspec(
        8, 2, height_ratios=[1.45, 0.25, 1.0, 1.0, 1.0, 1.0, 1.0, 1.15]
    )
    _render_header(fig.add_subplot(grid[0:2, :]), artifact, selected)

    for index, position in enumerate(artifact.positions):
        card = fig.add_subplot(grid[2 + index // 2, index % 2])
        _render_card(card, index, position, selected, FancyBboxPatch)

    curve_ax = fig.add_subplot(grid[7, :])
    _render_curve(curve_ax, performance, selected)
    fig.subplots_adjust(left=0.05, right=0.95, top=0.98, bottom=0.04, hspace=0.35, wspace=0.12)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, facecolor=selected.surface, bbox_inches="tight")
    plt.close(fig)
    return output


__all__ = ["render_basket_png"]
