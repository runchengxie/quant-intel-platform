"""Render a compact editorial PNG for the weekly basket."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .report_theme import ReportTheme, get_report_theme
from .weekly_client_basket import BasketArtifact
from .weekly_client_basket_render import STATUS_LABELS


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
        0.72,
        "周度组合 10",
        transform=ax.transAxes,
        fontsize=27,
        fontproperties=cjk_display,
        color=theme.ink,
        va="top",
    )
    ax.text(
        0.02,
        0.31,
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
        0.31,
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
        [0.14, 0.14],
        transform=ax.transAxes,
        color=theme.rule,
        linewidth=0.8,
    )
    ax.text(
        0.98,
        0.94,
        "历史时点重建",
        transform=ax.transAxes,
        fontsize=9,
        fontproperties=cjk_heavy,
        color=theme.accent,
        ha="right",
        va="top",
    )


def _render_holdings(ax, artifact: BasketArtifact, theme: ReportTheme) -> None:
    from .charts.theme import cjk, cjk_heavy

    ax.set_facecolor(theme.surface)
    ax.axis("off")
    sections = (
        ("现金流 6", [p for p in artifact.positions if p.source_strategy == "cashflow"], 0.98),
        ("微盘 4", [p for p in artifact.positions if p.source_strategy == "microcap"], 0.38),
    )
    for title, rows, title_y in sections:
        ax.text(
            0.02,
            title_y,
            title,
            transform=ax.transAxes,
            fontproperties=cjk_heavy,
            fontsize=13,
            color=theme.ink,
            va="top",
        )
        rule_y = title_y - 0.07
        ax.plot([0.02, 0.98], [rule_y, rule_y], transform=ax.transAxes, color=theme.rule, lw=0.8)
        row_height = 0.075
        for index, position in enumerate(rows, start=1):
            y = rule_y - (index - 0.5) * row_height
            _render_holding_row(
                ax, index, position, y, row_height, len(rows), theme, cjk, cjk_heavy
            )


def _render_holding_row(
    ax, index, position, y, row_height, row_count, theme, cjk, cjk_heavy
) -> None:
    ax.text(
        0.03,
        y,
        f"{index:02d}",
        transform=ax.transAxes,
        fontproperties=cjk,
        fontsize=9,
        color=theme.accent,
        va="center",
    )
    ax.text(
        0.11,
        y,
        position.name or "未命名",
        transform=ax.transAxes,
        fontproperties=cjk_heavy,
        fontsize=11,
        color=theme.ink,
        va="center",
    )
    ax.text(
        0.58,
        y,
        position.symbol,
        transform=ax.transAxes,
        fontproperties=cjk,
        fontsize=9,
        color=theme.muted,
        va="center",
    )
    status = STATUS_LABELS.get(position.status, position.status)
    ax.text(
        0.96,
        y,
        status,
        transform=ax.transAxes,
        fontproperties=cjk,
        fontsize=8.5,
        color=theme.accent if position.status == "NEW" else theme.muted,
        ha="right",
        va="center",
    )
    if index < row_count:
        line_y = y - row_height / 2
        ax.plot(
            [0.03, 0.97],
            [line_y, line_y],
            transform=ax.transAxes,
            color=theme.rule,
            lw=0.45,
            alpha=0.7,
        )


def _render_curve(curve_ax, performance: Mapping[str, object] | None, theme: ReportTheme) -> None:
    from .charts.theme import cjk, cjk_heavy

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
        x_values = list(range(len(values)))
        curve_ax.plot(x_values, values, color=theme.accent, linewidth=2.2, label="6+4 组合")
        raw_benchmark = (performance or {}).get("benchmark", [])
        if isinstance(raw_benchmark, list) and len(raw_benchmark) == len(values):
            benchmark = [float(cast(Mapping[str, Any], row)["nav"]) for row in raw_benchmark]
            benchmark_name = str(
                (performance or {}).get("benchmark_name", "沪深300价格指数（不含股息）")
            )
            curve_ax.plot(
                x_values,
                benchmark,
                color=theme.muted,
                linewidth=1.4,
                linestyle="--",
                label=benchmark_name,
            )
        curve_ax.fill_between(x_values, values, min(values), color=theme.accent, alpha=0.08)
        curve_ax.set_title(
            f"历史时点重建回测 · 60/40 袖内等权 · 截止 {series[-1]['date']}",
            loc="left",
            color=theme.ink,
            fontsize=12,
            fontproperties=cjk_heavy,
            pad=36,
        )
        metrics = (performance or {}).get("metrics", {})
        metric_values = (
            ("累计收益", float(cast(Mapping[str, Any], metrics).get("total_return", 0.0)), "%"),
            (
                "年化收益",
                float(cast(Mapping[str, Any], metrics).get("annualized_return", 0.0)),
                "%",
            ),
            ("最大回撤", float(cast(Mapping[str, Any], metrics).get("max_drawdown", 0.0)), "%"),
            ("样本周期", int(cast(Mapping[str, Any], metrics).get("observations", 0)), "期"),
        )
        metric_x = (0.02, 0.29, 0.56, 0.80)
        for index, (label, value, unit) in enumerate(metric_values):
            display = f"{value:+.1%}" if unit == "%" else f"{value} {unit}"
            curve_ax.text(
                metric_x[index],
                1.08,
                f"{label}  {display}",
                transform=curve_ax.transAxes,
                fontproperties=cjk,
                fontsize=8.5,
                color=theme.accent if index == 0 else theme.ink,
            )
        curve_ax.legend(loc="upper left", frameon=False, prop=cjk, fontsize=8)
        tick_indexes = sorted({0, len(values) // 2, len(values) - 1})
        curve_ax.set_xticks(tick_indexes)
        tick_labels = []
        for index in tick_indexes:
            date = str(series[index]["date"]).replace("-", "")
            tick_labels.append(f"{date[:4]}-{date[4:6]}")
        curve_ax.set_xticklabels(tick_labels)
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

    plt.rcParams["font.sans-serif"] = ["Source Han Sans CN", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    output = Path(output_path).expanduser().resolve()
    raw_series = (performance or {}).get("series", [])
    has_performance = isinstance(raw_series, list) and bool(raw_series)
    figure_height = 13.5 if has_performance else 11.8
    fig = plt.figure(figsize=(12.0, figure_height), dpi=140, facecolor=selected.surface)
    ratios = [1.2, 5.1, 2.5 if has_performance else 0.5]
    grid = fig.add_gridspec(3, 1, height_ratios=ratios)
    _render_header(fig.add_subplot(grid[0]), artifact, selected)
    _render_holdings(fig.add_subplot(grid[1]), artifact, selected)

    if has_performance:
        curve_ax = fig.add_subplot(grid[2])
        _render_curve(curve_ax, performance, selected)
        methodology = cast(Mapping[str, Any], (performance or {}).get("methodology", {}))
        footer = (
            "Research Observation · 历史时点重建回测 · "
            f"{float(methodology.get('cost_bps', 0.0)):.1f} bps · "
            "不代表实盘历史 · 不构成投资建议"
        )
    else:
        footer = "Research Observation · 历史净值暂不可用 · 不代表实盘历史 · 不构成投资建议"
    fig.text(
        0.05,
        0.018,
        footer,
        color=selected.muted,
        fontsize=7.5,
    )
    fig.subplots_adjust(left=0.07, right=0.93, top=0.98, bottom=0.06, hspace=0.30)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, facecolor=selected.surface, bbox_inches="tight")
    plt.close(fig)
    return output


__all__ = ["render_basket_png"]
