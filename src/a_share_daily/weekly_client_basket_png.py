"""Render a compact editorial PNG for the weekly basket."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .report_theme import ReportTheme, get_report_theme
from .weekly_client_basket import BasketArtifact
from .weekly_client_basket_render import SLEEVE_LABELS, STATUS_LABELS


def _render_header(ax, artifact: BasketArtifact, theme: ReportTheme) -> None:
    from .charts.theme import cjk, cjk_display, cjk_heavy

    ax.set_facecolor(theme.surface)
    ax.axis("off")
    ax.text(
        0.02,
        0.94,
        "WEEKLY PORTFOLIO",
        transform=ax.transAxes,
        fontsize=9,
        fontproperties=cjk_heavy,
        color=theme.accent,
        va="top",
    )
    ax.text(
        0.02,
        0.78,
        "周度组合 10",
        transform=ax.transAxes,
        fontsize=27,
        fontproperties=cjk_display,
        color=theme.ink,
        va="top",
    )
    ax.text(
        0.02,
        0.58,
        "WEEKLY CLIENT BASKET  ·  "
        f"{artifact.report_date[:4]}-{artifact.report_date[4:6]}-{artifact.report_date[6:]}",
        transform=ax.transAxes,
        fontsize=10,
        fontproperties=cjk,
        color=theme.muted,
        va="top",
    )
    ax.text(
        0.98,
        0.58,
        "现金流 6 + 微盘 4 · 周内冻结 · 研究观察",
        transform=ax.transAxes,
        fontsize=10,
        fontproperties=cjk,
        color=theme.muted,
        ha="right",
        va="top",
    )
    ax.plot(
        [0.02, 0.98],
        [0.47, 0.47],
        transform=ax.transAxes,
        color=theme.rule,
        linewidth=0.8,
    )
    stats = (
        ("总持仓", len(artifact.positions)),
        ("现金流", sum(p.source_strategy == "cashflow" for p in artifact.positions)),
        ("微盘", sum(p.source_strategy == "microcap" for p in artifact.positions)),
        ("本周新增", sum(p.status == "NEW" for p in artifact.positions)),
    )
    for index, (label, value) in enumerate(stats):
        x = 0.02 + index * 0.245
        ax.text(
            x,
            0.29,
            str(value),
            transform=ax.transAxes,
            fontsize=20,
            fontproperties=cjk_heavy,
            color=theme.accent if index in (0, 3) else theme.ink,
            va="center",
        )
        ax.text(
            x + 0.048,
            0.29,
            label,
            transform=ax.transAxes,
            fontsize=8.5,
            fontproperties=cjk,
            color=theme.muted,
            va="center",
        )
    ax.text(
        0.02,
        0.04,
        "本周组合",
        transform=ax.transAxes,
        fontsize=12,
        fontproperties=cjk_heavy,
        color=theme.ink,
        va="bottom",
    )


def _render_card(card, index: int, position, theme: ReportTheme, fancy_box) -> None:
    from .charts.theme import cjk, cjk_heavy

    card.set_facecolor(theme.panel)
    card.axis("off")
    card.add_patch(
        fancy_box(
            (0, 0),
            1,
            1,
            boxstyle="round,pad=0.012,rounding_size=0.015",
            linewidth=0.7,
            edgecolor=theme.rule,
            facecolor=theme.panel,
            transform=card.transAxes,
        )
    )
    card.plot(
        [0.025, 0.025],
        [0.12, 0.88],
        transform=card.transAxes,
        color=theme.accent,
        linewidth=2.0,
        solid_capstyle="round",
    )
    card.text(
        0.06,
        0.76,
        f"{index + 1:02d}",
        transform=card.transAxes,
        fontsize=10,
        fontproperties=cjk,
        color=theme.muted,
    )
    card.text(
        0.18,
        0.76,
        position.name or "未命名",
        transform=card.transAxes,
        fontsize=12,
        fontproperties=cjk_heavy,
        color=theme.ink,
    )
    card.text(
        0.18,
        0.52,
        position.symbol,
        transform=card.transAxes,
        fontsize=8.5,
        fontproperties=cjk,
        color=theme.muted,
    )
    card.text(
        0.06,
        0.17,
        SLEEVE_LABELS.get(position.source_strategy, position.source_strategy),
        transform=card.transAxes,
        fontsize=8,
        fontproperties=cjk,
        color=theme.muted,
    )
    card.text(
        0.90,
        0.18,
        STATUS_LABELS.get(position.status, position.status),
        transform=card.transAxes,
        fontsize=8,
        fontproperties=cjk,
        ha="right",
        color=theme.accent if position.status == "NEW" else theme.muted,
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
            1.0,
            1.04,
            f"{values[-1] / values[0] - 1:+.2%}",
            transform=curve_ax.transAxes,
            ha="right",
            color=theme.accent,
        )
    else:
        curve_ax.text(
            0.02,
            0.5,
            "历史净值：等待 provider performance.json",
            color=theme.muted,
            transform=curve_ax.transAxes,
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
    raw_series = (performance or {}).get("series", [])
    has_performance = isinstance(raw_series, list) and bool(raw_series)
    figure_height = 13.5 if has_performance else 12.2
    fig = plt.figure(figsize=(12.0, figure_height), dpi=140, facecolor=selected.surface)
    rows = 8 if has_performance else 7
    ratios = [1.25, 0.22, 1.0, 1.0, 1.0, 1.0, 1.0]
    if has_performance:
        ratios.append(1.15)
    grid = fig.add_gridspec(rows, 2, height_ratios=ratios)
    _render_header(fig.add_subplot(grid[0:2, :]), artifact, selected)

    for index, position in enumerate(artifact.positions):
        card = fig.add_subplot(grid[2 + index // 2, index % 2])
        _render_card(card, index, position, selected, FancyBboxPatch)

    if has_performance:
        curve_ax = fig.add_subplot(grid[7, :])
        _render_curve(curve_ax, performance, selected)
    else:
        fig.text(
            0.05,
            0.018,
            "Research Shadow · 历史净值暂不可用 · 仅供研究观察，不构成投资建议",
            color=selected.muted,
            fontsize=7.5,
        )
    fig.subplots_adjust(left=0.05, right=0.95, top=0.98, bottom=0.05, hspace=0.24, wspace=0.10)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, facecolor=selected.surface, bbox_inches="tight")
    plt.close(fig)
    return output


__all__ = ["render_basket_png"]
