"""Portfolio table and chart rendering for reconstructed cashflow snapshots."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, cast


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
        item["industry"] = str(industries.get(symbol) or item.get("industry") or "æªåç±»").strip()
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
        industry = str(row.get("industry") or "æªåç±»")
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
        "ð ç°éæµè´¨éç­ç¥ï½ç ç©¶ç»åå¿«ç§",
        "",
        "**RESEARCH ONLY Â· RECONSTRUCTED PIT Â· ä¸æææèµå»ºè®®**",
        "",
        f"ä¿¡å·ï¼{_date_dash(artifact['source_date'])} æ¶ç â {_date_dash(artifact['signal_date'])} å¼ç",
        f"ç­ç¥ï¼`{artifact['strategy_id']}`",
        f"PIT è´¨éï¼**{pit_quality} PIT**",
        f"åéæ°ï¼{artifact.get('candidate_count', 'n/a')}ï½å¥éæ°ï¼{artifact.get('selected_count', len(targets))}ï½"
        f"Top5 æéï¼{top5_weight:.1%}ï½æå¤§åæéï¼{max_weight:.1%}",
        f"æ¬æ¬¡æ°å¢ï¼{new_count} åªï½åç§°æ å°ï¼{artifact.get('named_targets', 'æªåºå®')}",
        "",
        "### è¡ä¸åå¸",
        "",
        f"è¡ä¸æ°ï¼{len(industries)}",
        "| Industry | Holdings | Weight |",
        "|---|---:|---:|",
        *[
            f"| {industry} | {count} | {weight:.1%} |"
            for industry, weight, count in industries[:10]
        ],
        "",
        "### ç»åæä»",
        "",
        "| Rank | Company | Code | Target weight |",
        "|---:|---|---|---:|",
    ]
    for row in targets:
        lines.append(
            f"| {int(row.get('selection_rank', 0))} | {row.get('name') or 'â'} | "
            f"{str(row.get('symbol', '')).split('.')[0]} | {float(row['target_weight']):.1%} |"
        )
    lines.extend(
        [
            "",
            "```text",
            "ç°éæµç¹å¾ â è´¨é/åé·é±ç­é â FCF capped weights â ç ç©¶ç»å",
            "      â              â                  â                 â",
            "```",
            "",
            "â ï¸ **ç ç©¶å¿«ç§**ï¼ä½¿ç¨ reconstructed PITï¼`eligible_for_live=false`ã",
            "ç»æå¯è½åå«åå²ä¿®è®¢åå·®ï¼ä¸æææèµå»ºè®®æå®çæä»¤ã",
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
        "ð ç°éæµè´¨éç­ç¥ï½å¯æ§è¡ç»åå¿«ç§",
        "",
        "**RESEARCH ONLY Â· RECONSTRUCTED PIT Â· ä¸æææèµå»ºè®®**",
        "",
        f"ä¿¡å·ï¼{_date_dash(artifact['source_date'])} æ¶ç â {_date_dash(artifact['signal_date'])} å¼ç",
        f"ä»·æ ¼æ¥æï¼{_date_dash(artifact.get('price_date', artifact['source_date']))}ï½ç­ç¥ï¼`{artifact['strategy_id']}`",
        f"åèèµéï¼Â¥{portfolio_value:,.0f}ï½æå¥ï¼Â¥{invested_amount:,.0f} ({invested_amount / portfolio_value:.1%})ï½"
        f"ç°éï¼Â¥{cash_amount:,.0f} ({cash_amount / portfolio_value:.1%})",
        f"ç ç©¶åéï¼{artifact.get('candidate_count', 'n/a')}ï½å¯æ§è¡æä»ï¼{len(targets)}ï½"
        f"æå¤§åè¡ï¼{max(float(row.get('actual_weight', 0.0)) for row in targets):.1%}",
        "",
        "### è¡ä¸åå¸",
        "",
        "| Industry | Holdings | Actual weight |",
        "|---|---:|---:|",
        *[
            f"| {industry} | {count} | {weight:.1%} |"
            for industry, weight, count in industries[:10]
        ],
        "",
        "### å¯æ§è¡æä»",
        "",
        "| Rank | Company | Code | Shares | Target amount | Actual amount | Actual weight | æéåå·® |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in targets:
        lines.append(
            f"| {int(row.get('selection_rank', 0))} | {row.get('name') or 'â'} | "
            f"{str(row.get('symbol', '')).split('.')[0]} | {int(row.get('shares', 0)):,} | "
            f"Â¥{float(row.get('target_amount', 0.0)):,.0f} | "
            f"Â¥{float(row.get('actual_amount', 0.0)):,.0f} | "
            f"{float(row.get('actual_weight', 0.0)):.1%} | "
            f"{float(row.get('weight_deviation', 0.0)):+.1%} |"
        )
    skipped = artifact.get("skipped", [])
    if skipped:
        lines.extend(["", "### è·³è¿è¯æ­", "", "| Code | Reason |", "|---|---|"])
        lines.extend(
            f"| {item.get('symbol', 'â')} | {item.get('reason', 'â')} |" for item in skipped
        )
    lines.extend(
        [
            "",
            "```text",
            "Top 50 research ranking â lot rounding â executable research portfolio",
            "             â                  â                    â",
            "```",
            "",
            "â ï¸ **ç ç©¶å¿«ç§**ï¼ä½¿ç¨ reconstructed PITï¼`eligible_for_live=false`ã",
            "å®éè¡æ°ä»ç¨äºç ç©¶æ¨¡æï¼ä¸ææå®çæä»¤ã",
        ]
    )
    return "\n".join(lines) + "\n"


def render_cashflow_portfolio_png(  # noqa: PLR0915
    artifact: Mapping[str, Any], output_path: str | Path
) -> Path:
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

    labels = [
        f"{row.get('name') or 'â'}\n{str(row.get('symbol', '')).split('.')[0]}" for row in targets
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
        kicker="CASHFLOW QUALITY Â· RESEARCH SNAPSHOT",
        title="ç°éæµè´¨éç­ç¥ï½ç ç©¶ç»å",
        subtitle=(
            f"{_date_dash(artifact['source_date'])} æ¶ç â {_date_dash(artifact['signal_date'])} å¼ç"
            " Â· reconstructed PIT Â· ä»ä¾ç ç©¶è§å¯"
        ),
    )
    status_ax = fig.add_subplot(grid[1, :])
    status_ax.axis("off")
    status_ax.text(
        0.0,
        0.45,
        "â RESEARCH ONLY",
        color=YELLOW,
        fontsize=10,
        fontproperties=cjk,
        fontweight="bold",
    )
    status_ax.text(
        0.20,
        0.45,
        f"åé {artifact.get('candidate_count', 'n/a')}  Â·  å¥é {len(targets)}  Â·  "
        f"Top5 {sum(weights[:5]):.1f}%  Â·  Max {max(weights):.1f}%",
        color=FG,
        fontsize=10,
        fontproperties=cjk,
    )
    ax = fig.add_subplot(grid[2, 0])
    industry_ax = fig.add_subplot(grid[2, 1])
    positions = list(range(len(labels)))[::-1]
    ax.barh(positions, weights[::-1], color=colors[::-1], edgecolor="none")
    ax.set_yticks(positions, labels[::-1], fontproperties=cjk)
    ax.set_xlabel("Target weight (%)", fontproperties=cjk)
    ax.set_xlim(0, max(weights) * 1.25 if weights else 1)
    style_plot_axes(ax, grid_axis="x")
    for position, weight in zip(positions, weights[::-1], strict=True):
        ax.text(
            weight + 0.5,
            position,
            f"{weight:.1f}%",
            va="center",
            fontsize=10,
            fontproperties=cjk,
        )
    industry_rows = _industry_breakdown(targets)[:8]
    industry_labels = [row[0] for row in industry_rows][::-1]
    industry_weights = [row[1] * 100 for row in industry_rows][::-1]
    industry_counts = [row[2] for row in industry_rows][::-1]
    industry_positions = list(range(len(industry_labels)))
    industry_ax.barh(industry_positions, industry_weights, color="#7aa9e8", edgecolor="none")
    industry_ax.set_yticks(industry_positions, industry_labels, fontproperties=cjk)
    industry_ax.set_xlabel("Industry weight (%)", fontproperties=cjk)
    industry_ax.set_title("è¡ä¸åå¸ Â· Top 8", loc="left", fontproperties=cjk, color=FG)
    industry_ax.set_xlim(0, max(industry_weights) * 1.3 if industry_weights else 1)
    style_plot_axes(industry_ax, grid_axis="x")
    for position, weight, count in zip(
        industry_positions, industry_weights, industry_counts, strict=True
    ):
        industry_ax.text(
            weight + 0.25,
            position,
            f"{weight:.1f}% Â· {count}åª",
            va="center",
            fontsize=9,
            fontproperties=cjk,
        )
    fig.text(
        0.06,
        0.025,
        "ä½¿ç¨ reconstructed PITï¼å¯è½å­å¨åå²ä¿®è®¢åå·®ï¼ä»ä¾ç ç©¶è§å¯ï¼ä¸æææèµå»ºè®®ã",
        fontsize=9,
        color=MUTED,
        fontproperties=cjk,
    )
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.{os.getpid()}.tmp{output.suffix}")
    try:
        fig.savefig(temporary, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        temporary.replace(output)
    finally:
        plt.close(fig)
        temporary.unlink(missing_ok=True)
    return output


def _draw_executable_holdings(
    ax: Any,
    top_targets: list[Mapping[str, Any]],
    *,
    accent: str,
    fg: str,
    cjk: Any,
    style_plot_axes: Any,
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
        color=[accent if i < 3 else "#7aa9e8" for i in positions],
        edgecolor="none",
    )
    ax.set_yticks(positions, labels, fontproperties=cjk)
    ax.set_xlabel("Actual weight (%)", fontproperties=cjk)
    ax.set_title("Top 10 可执行持仓", loc="left", fontproperties=cjk, color=fg)
    ax.set_xlim(0, max(weights) * 1.25 if weights else 1)
    style_plot_axes(ax, grid_axis="x")
    for position, weight in zip(positions, weights, strict=True):
        ax.text(weight + 0.25, position, f"{weight:.1f}%", va="center", fontsize=9)


def _draw_executable_industries(
    ax: Any,
    industry_rows: list[tuple[str, float, int]],
    *,
    fg: str,
    cjk: Any,
    style_plot_axes: Any,
) -> None:
    industry_labels = [row[0] for row in reversed(industry_rows)]
    industry_weights = [row[1] * 100 for row in reversed(industry_rows)]
    industry_counts = [row[2] for row in reversed(industry_rows)]
    industry_positions = list(range(len(industry_labels)))
    ax.barh(industry_positions, industry_weights, color="#7aa9e8", edgecolor="none")
    ax.set_yticks(industry_positions, industry_labels, fontproperties=cjk)
    ax.set_xlabel("Actual weight (%)", fontproperties=cjk)
    ax.set_title("行业分布 · Top 8 + Other", loc="left", fontproperties=cjk, color=fg)
    ax.set_xlim(0, max(industry_weights) * 1.3 if industry_weights else 1)
    style_plot_axes(ax, grid_axis="x")
    for position, weight, count in zip(
        industry_positions, industry_weights, industry_counts, strict=True
    ):
        ax.text(
            weight + 0.25,
            position,
            f"{weight:.1f}% · {count}只",
            va="center",
            fontsize=9,
            fontproperties=cjk,
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
        kicker="CASHFLOW QUALITY Â· EXECUTABLE RESEARCH SNAPSHOT",
        title="ç°éæµè´¨éç­ç¥ï½å¯æ§è¡ç»å",
        subtitle=(
            f"{_date_dash(artifact['source_date'])} æ¶ç â {_date_dash(artifact['signal_date'])} å¼ç"
            f" Â· ä»·æ ¼ {_date_dash(artifact.get('price_date', artifact['source_date']))} Â· reconstructed PIT"
        ),
    )
    status_ax = fig.add_subplot(grid[1, :])
    status_ax.axis("off")
    status_ax.text(
        0.0,
        0.62,
        "â RESEARCH ONLY",
        color=YELLOW,
        fontsize=10,
        fontproperties=cjk,
        fontweight="bold",
    )
    status_ax.text(
        0.18,
        0.62,
        f"æä» {len(targets)}  Â·  æå¥ {invested_amount / portfolio_value:.1%}  Â· ç°é {cash_amount / portfolio_value:.1%}  Â· "
        f"Max {max(float(row.get('actual_weight', 0.0)) for row in targets):.1%}",
        color=FG,
        fontsize=10,
        fontproperties=cjk,
    )
    _draw_executable_holdings(
        fig.add_subplot(grid[2, 0]),
        top_targets,
        accent=ACCENT,
        fg=FG,
        cjk=cjk,
        style_plot_axes=style_plot_axes,
    )
    _draw_executable_industries(
        fig.add_subplot(grid[2, 1]),
        industry_rows,
        fg=FG,
        cjk=cjk,
        style_plot_axes=style_plot_axes,
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
        "ä½¿ç¨ reconstructed PITï¼å®éè¡æ°ä¸ºç ç©¶æ¨¡æï¼eligible_for_live=falseï¼ä¸æææèµå»ºè®®ã",
        fontsize=9,
        color=MUTED,
        fontproperties=cjk,
    )
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.{os.getpid()}.tmp{output.suffix}")
    try:
        fig.savefig(temporary, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        temporary.replace(output)
    finally:
        plt.close(fig)
        temporary.unlink(missing_ok=True)
    return output


__all__ = [
    "enrich_cashflow_portfolio",
    "render_cashflow_portfolio_markdown",
    "render_cashflow_portfolio_png",
]
