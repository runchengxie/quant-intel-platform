"""Portfolio table and chart rendering for reconstructed cashflow snapshots."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class _PortfolioChartStyle:
    accent: str
    background: str
    foreground: str
    muted: str
    warning: str
    cjk: Any
    style_plot_axes: Any


@dataclass(frozen=True)
class _CashflowChartStatus:
    artifact: Mapping[str, Any]
    targets: list[Mapping[str, Any]]
    weights: list[float]


@dataclass(frozen=True)
class _ExecutableChartStatus:
    targets: list[Mapping[str, Any]]
    portfolio_value: float
    invested_amount: float
    cash_amount: float


def _date_dash(value: Any) -> str:
    text = str(value).replace("-", "")
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _targets(artifact: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    targets = artifact.get("targets")
    if (
        not isinstance(targets, list)
        or not targets
        or not all(isinstance(row, Mapping) for row in targets)
    ):
        raise ValueError("cashflow portfolio targets must be a non-empty list")
    return cast(list[Mapping[str, Any]], targets)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def enrich_cashflow_portfolio(
    artifact: Mapping[str, Any], instrument_snapshot: str | Path
) -> dict[str, Any]:
    """Pin company names from one instrument snapshot into a display artifact."""
    import pandas as pd

    path = Path(instrument_snapshot).expanduser().resolve()
    frame = pd.read_parquet(path)
    required = {"symbol", "name"}
    if not required.issubset(frame.columns):
        raise ValueError("instrument snapshot must contain symbol and name columns")
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["name"] = frame["name"].fillna("").astype(str).str.strip()
    names = dict(zip(frame["symbol"], frame["name"], strict=False))
    industries = (
        dict(
            zip(frame["symbol"], frame["industry"].fillna("").astype(str).str.strip(), strict=False)
        )
        if "industry" in frame.columns
        else {}
    )
    enriched = deepcopy(dict(artifact))
    targets = []
    for row in _targets(artifact):
        item = dict(row)
        symbol = str(item.get("symbol") or "").strip().upper()
        item["name"] = str(names.get(symbol) or item.get("name") or "").strip()
        item["industry"] = str(industries.get(symbol) or item.get("industry") or "未分类").strip()
        targets.append(item)
    enriched["targets"] = targets
    enriched["instrument_snapshot"] = str(path)
    enriched["instrument_snapshot_sha256"] = _sha256_file(path)
    enriched["named_targets"] = sum(bool(row.get("name")) for row in targets)
    return enriched


def _is_executable(artifact: Mapping[str, Any]) -> bool:
    return str(artifact.get("schema_version", "")).endswith("cashflow.executable.v1") or any(
        "actual_weight" in row for row in _targets(artifact)
    )


def _industry_breakdown(
    targets: list[Mapping[str, Any]], weight_field: str = "target_weight"
) -> list[tuple[str, float, int]]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in targets:
        industry = str(row.get("industry") or "未分类")
        totals[industry] = totals.get(industry, 0.0) + float(row.get(weight_field, 0.0))
        counts[industry] = counts.get(industry, 0) + 1
    return sorted(
        ((industry, weight, counts[industry]) for industry, weight in totals.items()),
        key=lambda item: (-item[1], item[0]),
    )


def render_cashflow_portfolio_markdown(artifact: Mapping[str, Any]) -> str:
    targets = _targets(artifact)
    if _is_executable(artifact):
        return _render_executable_markdown(artifact, targets)
    pit_quality = str(artifact.get("pit_quality") or "unknown").upper()
    top5_weight = sum(float(row.get("target_weight", 0.0)) for row in targets[:5])
    max_weight = max(float(row.get("target_weight", 0.0)) for row in targets)
    new_count = sum(bool(row.get("is_new")) for row in targets)
    industries = _industry_breakdown(targets)
    lines = [
        "📊 现金流质量策略｜研究组合快照",
        "",
        "**RESEARCH ONLY · RECONSTRUCTED PIT · 不构成投资建议**",
        "",
        f"信号：{_date_dash(artifact['source_date'])} 收盘 → {_date_dash(artifact['signal_date'])} 开盘",
        f"策略：`{artifact['strategy_id']}`",
        f"PIT 质量：**{pit_quality} PIT**",
        f"候选数：{artifact.get('candidate_count', 'n/a')}｜入选数：{artifact.get('selected_count', len(targets))}｜"
        f"Top5 权重：{top5_weight:.1%}｜最大单权重：{max_weight:.1%}",
        f"本次新增：{new_count} 只｜名称映射：{artifact.get('named_targets', '未固定')}",
        "",
        "### 行业分布",
        "",
        f"行业数：{len(industries)}",
        "| Industry | Holdings | Weight |",
        "|---|---:|---:|",
        *[
            f"| {industry} | {count} | {weight:.1%} |"
            for industry, weight, count in industries[:10]
        ],
        "",
        "### 组合持仓",
        "",
        "| Rank | Company | Code | Target weight |",
        "|---:|---|---|---:|",
    ]
    for row in targets:
        lines.append(
            f"| {int(row.get('selection_rank', 0))} | {row.get('name') or '—'} | "
            f"{str(row.get('symbol', '')).split('.')[0]} | {float(row['target_weight']):.1%} |"
        )
    lines.extend(
        [
            "",
            "```text",
            "现金流特征 → 质量/反陷阱筛选 → FCF capped weights → 研究组合",
            "      ✓              ✓                  ✓                 ✓",
            "```",
            "",
            "⚠️ **研究快照**：使用 reconstructed PIT；`eligible_for_live=false`。",
            "结果可能包含历史修订偏差，不构成投资建议或实盘指令。",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_executable_markdown(
    artifact: Mapping[str, Any], targets: list[Mapping[str, Any]]
) -> str:
    policy_value = artifact.get("policy")
    policy: Mapping[str, Any] = (
        cast(Mapping[str, Any], policy_value) if isinstance(policy_value, Mapping) else {}
    )
    portfolio_value = float(policy.get("portfolio_value", 0.0))
    invested_amount = float(artifact.get("invested_amount", 0.0))
    cash_amount = float(artifact.get("cash_amount", portfolio_value - invested_amount))
    industries = _industry_breakdown(targets, "actual_weight")
    lines = [
        "📊 现金流质量策略｜可执行组合快照",
        "",
        "**RESEARCH ONLY · RECONSTRUCTED PIT · 不构成投资建议**",
        "",
        f"信号：{_date_dash(artifact['source_date'])} 收盘 → {_date_dash(artifact['signal_date'])} 开盘",
        f"价格日期：{_date_dash(artifact.get('price_date', artifact['source_date']))}｜策略：`{artifact['strategy_id']}`",
        f"参考资金：¥{portfolio_value:,.0f}｜投入：¥{invested_amount:,.0f} ({invested_amount / portfolio_value:.1%})｜"
        f"现金：¥{cash_amount:,.0f} ({cash_amount / portfolio_value:.1%})",
        f"研究候选：{artifact.get('candidate_count', 'n/a')}｜可执行持仓：{len(targets)}｜"
        f"最大单股：{max(float(row.get('actual_weight', 0.0)) for row in targets):.1%}",
        "",
        "### 行业分布",
        "",
        "| Industry | Holdings | Actual weight |",
        "|---|---:|---:|",
        *[
            f"| {industry} | {count} | {weight:.1%} |"
            for industry, weight, count in industries[:10]
        ],
        "",
        "### 可执行持仓",
        "",
        "| Rank | Company | Code | Shares | Target amount | Actual amount | Actual weight | 权重偏差 |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in targets:
        lines.append(
            f"| {int(row.get('selection_rank', 0))} | {row.get('name') or '—'} | "
            f"{str(row.get('symbol', '')).split('.')[0]} | {int(row.get('shares', 0)):,} | "
            f"¥{float(row.get('target_amount', 0.0)):,.0f} | "
            f"¥{float(row.get('actual_amount', 0.0)):,.0f} | "
            f"{float(row.get('actual_weight', 0.0)):.1%} | "
            f"{float(row.get('weight_deviation', 0.0)):+.1%} |"
        )
    skipped = artifact.get("skipped", [])
    if skipped:
        lines.extend(["", "### 跳过诊断", "", "| Code | Reason |", "|---|---|"])
        lines.extend(
            f"| {item.get('symbol', '—')} | {item.get('reason', '—')} |" for item in skipped
        )
    lines.extend(
        [
            "",
            "```text",
            "Top 50 research ranking → lot rounding → executable research portfolio",
            "             ✓                  ✓                    ✓",
            "```",
            "",
            "⚠️ **研究快照**：使用 reconstructed PIT；`eligible_for_live=false`。",
            "实际股数仅用于研究模拟，不构成实盘指令。",
        ]
    )
    return "\n".join(lines) + "\n"


def _save_chart_png(fig: Any, output_path: str | Path, pyplot: Any) -> Path:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.{os.getpid()}.tmp{output.suffix}")
    try:
        fig.savefig(temporary, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        temporary.replace(output)
    finally:
        pyplot.close(fig)
        temporary.unlink(missing_ok=True)
    return output


def _draw_cashflow_holdings(
    ax: Any,
    labels: list[str],
    weights: list[float],
    colors: list[str],
    style: _PortfolioChartStyle,
) -> None:
    positions = list(range(len(labels)))[::-1]
    ax.barh(positions, weights[::-1], color=colors[::-1], edgecolor="none")
    ax.set_yticks(positions, labels[::-1], fontproperties=style.cjk)
    ax.set_xlabel("Target weight (%)", fontproperties=style.cjk)
    ax.set_xlim(0, max(weights) * 1.25 if weights else 1)
    style.style_plot_axes(ax, grid_axis="x")
    for position, weight in zip(positions, weights[::-1], strict=True):
        ax.text(
            weight + 0.5,
            position,
            f"{weight:.1f}%",
            va="center",
            fontsize=10,
            fontproperties=style.cjk,
        )


def _draw_cashflow_industries(
    ax: Any,
    labels: list[str],
    weights: list[float],
    counts: list[int],
    style: _PortfolioChartStyle,
) -> None:
    positions = list(range(len(labels)))
    ax.barh(positions, weights, color="#7aa9e8", edgecolor="none")
    ax.set_yticks(positions, labels, fontproperties=style.cjk)
    ax.set_xlabel("Industry weight (%)", fontproperties=style.cjk)
    ax.set_xlim(0, max(weights) * 1.3 if weights else 1)
    style.style_plot_axes(ax, grid_axis="x")
    for position, weight, count in zip(positions, weights, counts, strict=True):
        ax.text(
            weight + 0.25,
            position,
            f"{weight:.1f}% · {count}只",
            va="center",
            fontsize=9,
            fontproperties=style.cjk,
        )


def _add_cashflow_status(
    fig: Any,
    grid: Any,
    status: _CashflowChartStatus,
    style: _PortfolioChartStyle,
) -> None:
    status_ax = fig.add_subplot(grid[1, :])
    status_ax.axis("off")
    status_ax.text(
        0.0,
        0.45,
        "● RESEARCH ONLY",
        color=style.warning,
        fontsize=10,
        fontproperties=style.cjk,
        fontweight="bold",
    )
    status_ax.text(
        0.20,
        0.45,
        f"候选 {status.artifact.get('candidate_count', 'n/a')}  ·  入选 {len(status.targets)}  ·  "
        f"Top5 {sum(status.weights[:5]):.1f}%  ·  Max {max(status.weights):.1f}%",
        color=style.foreground,
        fontsize=10,
        fontproperties=style.cjk,
    )


def render_cashflow_portfolio_png(artifact: Mapping[str, Any], output_path: str | Path) -> Path:
    """Render a DailyWatch-style allocation chart from a passed selection artifact."""
    targets = _targets(artifact)
    if _is_executable(artifact):
        return _render_executable_png(artifact, output_path, targets)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from a_share_daily.charts.theme import (
        ACCENT,
        BG,
        FG,
        MUTED,
        YELLOW,
        add_report_header,
        apply_graph_paper,
        cjk,
        style_plot_axes,
    )

    style = _PortfolioChartStyle(ACCENT, BG, FG, MUTED, YELLOW, cjk, style_plot_axes)

    labels = [
        f"{row.get('name') or '—'}\n{str(row.get('symbol', '')).split('.')[0]}" for row in targets
    ]
    weights = [float(row["target_weight"]) * 100 for row in targets]
    colors = [ACCENT if index < 5 else "#7aa9e8" for index in range(len(targets))]
    height = max(8.5, 4.5 + len(targets) * 0.38)
    fig = plt.figure(figsize=(15, height), facecolor=BG)
    apply_graph_paper(fig)
    grid = fig.add_gridspec(
        4,
        2,
        left=0.07,
        right=0.96,
        top=0.86,
        bottom=0.045,
        height_ratios=(0.55, 0.35, 7.2, 0.35),
        width_ratios=(2.5, 1),
        hspace=0.24,
        wspace=0.28,
    )
    add_report_header(
        fig,
        kicker="CASHFLOW QUALITY · RESEARCH SNAPSHOT",
        title="现金流质量策略｜研究组合",
        subtitle=(
            f"{_date_dash(artifact['source_date'])} 收盘 → {_date_dash(artifact['signal_date'])} 开盘"
            " · reconstructed PIT · 仅供研究观察"
        ),
    )
    _add_cashflow_status(fig, grid, _CashflowChartStatus(artifact, targets, weights), style)
    ax = fig.add_subplot(grid[2, 0])
    industry_ax = fig.add_subplot(grid[2, 1])
    _draw_cashflow_holdings(
        ax,
        labels,
        weights,
        colors,
        style,
    )
    industry_rows = _industry_breakdown(targets)[:8]
    industry_labels = [row[0] for row in industry_rows][::-1]
    industry_weights = [row[1] * 100 for row in industry_rows][::-1]
    industry_counts = [row[2] for row in industry_rows][::-1]
    industry_ax.set_title("行业分布 · Top 8", loc="left", fontproperties=cjk, color=FG)
    _draw_cashflow_industries(
        industry_ax,
        industry_labels,
        industry_weights,
        industry_counts,
        style,
    )
    fig.text(
        0.06,
        0.025,
        "使用 reconstructed PIT；可能存在历史修订偏差；仅供研究观察，不构成投资建议。",
        fontsize=9,
        color=MUTED,
        fontproperties=cjk,
    )
    return _save_chart_png(fig, output_path, plt)


def _draw_executable_holdings(
    ax: Any,
    top_targets: list[Mapping[str, Any]],
    style: _PortfolioChartStyle,
) -> None:
    labels = [
        f"{row.get('name') or '—'}\n{str(row.get('symbol', '')).split('.')[0]}"
        for row in reversed(top_targets)
    ]
    weights = [float(row.get("actual_weight", 0.0)) * 100 for row in reversed(top_targets)]
    positions = list(range(len(labels)))
    ax.barh(
        positions,
        weights,
        color=[style.accent if i < 3 else "#7aa9e8" for i in positions],
        edgecolor="none",
    )
    ax.set_yticks(positions, labels, fontproperties=style.cjk)
    ax.set_xlabel("Actual weight (%)", fontproperties=style.cjk)
    ax.set_title("Top 10 可执行持仓", loc="left", fontproperties=style.cjk, color=style.foreground)
    ax.set_xlim(0, max(weights) * 1.25 if weights else 1)
    style.style_plot_axes(ax, grid_axis="x")
    for position, weight in zip(positions, weights, strict=True):
        ax.text(weight + 0.25, position, f"{weight:.1f}%", va="center", fontsize=9)


def _draw_executable_industries(
    ax: Any,
    industry_rows: list[tuple[str, float, int]],
    style: _PortfolioChartStyle,
) -> None:
    industry_labels = [row[0] for row in reversed(industry_rows)]
    industry_weights = [row[1] * 100 for row in reversed(industry_rows)]
    industry_counts = [row[2] for row in reversed(industry_rows)]
    industry_positions = list(range(len(industry_labels)))
    ax.barh(industry_positions, industry_weights, color="#7aa9e8", edgecolor="none")
    ax.set_yticks(industry_positions, industry_labels, fontproperties=style.cjk)
    ax.set_xlabel("Actual weight (%)", fontproperties=style.cjk)
    ax.set_title(
        "行业分布 · Top 8 + Other", loc="left", fontproperties=style.cjk, color=style.foreground
    )
    ax.set_xlim(0, max(industry_weights) * 1.3 if industry_weights else 1)
    style.style_plot_axes(ax, grid_axis="x")
    for position, weight, count in zip(
        industry_positions, industry_weights, industry_counts, strict=True
    ):
        ax.text(
            weight + 0.25,
            position,
            f"{weight:.1f}% · {count}只",
            va="center",
            fontsize=9,
            fontproperties=style.cjk,
        )


def _draw_executable_table(
    ax: Any,
    top_targets: list[Mapping[str, Any]],
    *,
    bg: str,
    fg: str,
    cjk: Any,
) -> None:
    ax.axis("off")
    ax.set_title("执行明细 · 100股整手后", loc="left", fontproperties=cjk, color=fg, pad=8)
    table_rows = [
        [
            str(row.get("name") or "—"),
            str(row.get("symbol", "")).split(".")[0],
            f"{int(row.get('shares', 0)):,}",
            f"¥{float(row.get('actual_amount', 0.0)):,.0f}",
            f"{float(row.get('actual_weight', 0.0)):.1%}",
            f"{float(row.get('weight_deviation', 0.0)):+.1%}",
        ]
        for row in top_targets
    ]
    table = ax.table(
        cellText=table_rows,
        colLabels=["Company", "Code", "Shares", "Actual amount", "Actual weight", "Deviation"],
        loc="upper left",
        cellLoc="left",
        colWidths=[0.23, 0.13, 0.14, 0.19, 0.16, 0.15],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.35)
    for cell in table.get_celld().values():
        cell.set_edgecolor("#d7dde5")
        cell.set_facecolor(bg)
        cell.get_text().set_color(fg)
        cell.get_text().set_fontproperties(cjk)
    for (row_index, _), cell in table.get_celld().items():
        if row_index == 0:
            cell.set_facecolor("#e8eef7")


def _add_executable_status(
    fig: Any,
    grid: Any,
    status: _ExecutableChartStatus,
    style: _PortfolioChartStyle,
) -> None:
    status_ax = fig.add_subplot(grid[1, :])
    status_ax.axis("off")
    status_ax.text(
        0.0,
        0.62,
        "● RESEARCH ONLY",
        color=style.warning,
        fontsize=10,
        fontproperties=style.cjk,
        fontweight="bold",
    )
    status_ax.text(
        0.18,
        0.62,
        f"持仓 {len(status.targets)}  ·  投入 {status.invested_amount / status.portfolio_value:.1%}  · 现金 {status.cash_amount / status.portfolio_value:.1%}  · "
        f"Max {max(float(row.get('actual_weight', 0.0)) for row in status.targets):.1%}",
        color=style.foreground,
        fontsize=10,
        fontproperties=style.cjk,
    )


def _render_executable_png(
    artifact: Mapping[str, Any], output_path: str | Path, targets: list[Mapping[str, Any]]
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from a_share_daily.charts.theme import (
        ACCENT,
        BG,
        FG,
        MUTED,
        YELLOW,
        add_report_header,
        apply_graph_paper,
        cjk,
        style_plot_axes,
    )

    style = _PortfolioChartStyle(ACCENT, BG, FG, MUTED, YELLOW, cjk, style_plot_axes)

    policy_value = artifact.get("policy")
    policy: Mapping[str, Any] = (
        cast(Mapping[str, Any], policy_value) if isinstance(policy_value, Mapping) else {}
    )
    portfolio_value = float(policy.get("portfolio_value", 0.0))
    invested_amount = float(artifact.get("invested_amount", 0.0))
    cash_amount = float(artifact.get("cash_amount", portfolio_value - invested_amount))
    top_targets = sorted(
        targets,
        key=lambda row: (-float(row.get("actual_weight", 0.0)), int(row.get("selection_rank", 0))),
    )[:10]
    industry_rows = _industry_breakdown(targets, "actual_weight")
    if len(industry_rows) > 8:
        other_weight = sum(weight for _, weight, _ in industry_rows[8:])
        other_count = sum(count for _, _, count in industry_rows[8:])
        industry_rows = [*industry_rows[:8], ("Other", other_weight, other_count)]

    fig = plt.figure(figsize=(15, 11), facecolor=BG)
    apply_graph_paper(fig)
    grid = fig.add_gridspec(
        5,
        2,
        left=0.07,
        right=0.96,
        top=0.86,
        bottom=0.08,
        height_ratios=(0.5, 0.55, 3.0, 2.0, 0.25),
        width_ratios=(1.55, 1),
        hspace=0.45,
        wspace=0.3,
    )
    add_report_header(
        fig,
        kicker="CASHFLOW QUALITY · EXECUTABLE RESEARCH SNAPSHOT",
        title="现金流质量策略｜可执行组合",
        subtitle=(
            f"{_date_dash(artifact['source_date'])} 收盘 → {_date_dash(artifact['signal_date'])} 开盘"
            f" · 价格 {_date_dash(artifact.get('price_date', artifact['source_date']))} · reconstructed PIT"
        ),
    )
    _add_executable_status(
        fig,
        grid,
        _ExecutableChartStatus(targets, portfolio_value, invested_amount, cash_amount),
        style,
    )
    _draw_executable_holdings(
        fig.add_subplot(grid[2, 0]),
        top_targets,
        style,
    )
    _draw_executable_industries(
        fig.add_subplot(grid[2, 1]),
        industry_rows,
        style,
    )
    _draw_executable_table(
        fig.add_subplot(grid[3, :]),
        top_targets,
        bg=BG,
        fg=FG,
        cjk=cjk,
    )

    fig.text(
        0.06,
        0.035,
        "使用 reconstructed PIT；实际股数为研究模拟；eligible_for_live=false；不构成投资建议。",
        fontsize=9,
        color=MUTED,
        fontproperties=cjk,
    )
    return _save_chart_png(fig, output_path, plt)


__all__ = [
    "enrich_cashflow_portfolio",
    "render_cashflow_portfolio_markdown",
    "render_cashflow_portfolio_png",
]
