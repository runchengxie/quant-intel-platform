"""Light "graph-paper" DailyWatch20 PNG renderer.

Style borrowed from a reference infographic: warm paper-white background with a
faint graph-paper grid, a Source Han Serif display title + regular sans body,
and a restrained academic "lab-notebook" look.

Built on the shared :mod:`a_share_daily.charts.theme` (LIGHT default). The
original dark client sheet in :mod:`a_share_daily.daily_watch20_client_render`
remains available as the switchable dark variant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from a_share_daily.charts.theme import (
    LIGHT,
    add_report_header,
    apply_graph_paper,
    cjk,
    cjk_heavy,
)

from .daily_watch20 import DailyWatch20Artifact, _date_dash, _records, _regime_summary
from .daily_watch20_client_render import (
    CLIENT_DISCLAIMER,
    CLIENT_METHOD_SUMMARY,
    _client_candidate_data_warning,
    _group_share,
    _short_tokens,
    _truncate_display,
    _validate_client_frame_copy,
    _wrap_display_text,
    client_display_frame,
)

# ── Resolved light palette ─────────────────────────────────────────────────────
BG = LIGHT.BG
TEXT = LIGHT.FG
TEXT_SOFT = LIGHT.MUTED
MUTED = LIGHT.MUTED
LINE = LIGHT.LINE
ACCENT_BLUE = LIGHT.ACCENT
WARN = "#b8860b"


def _truncate(value: Any, width: int) -> str:
    text = str(value or "")
    if len(text) <= width:
        return text
    return text[: max(width - 1, 0)].rstrip() + "…"


def _light_overview(artifact: DailyWatch20Artifact) -> tuple[tuple[str, str], ...]:
    """Return the small client-safe facts shown below the editorial header."""
    new_count = int(artifact.frame["is_new"].astype(bool).sum())
    return (
        ("跟踪总数", f"{len(artifact.frame)} 只"),
        ("新增", f"{new_count} 只"),
        ("保留", f"{len(artifact.frame) - new_count} 只"),
    )


def _draw_light_header(fig: Any, artifact: DailyWatch20Artifact) -> None:
    add_report_header(
        fig,
        kicker=f"{_date_dash(artifact.signal_date)} · DAILYWATCH20 / DAILY FOCUS",
        title="今日20只重点关注",
        subtitle=(
            f"源数据 {_date_dash(artifact.source_date)} · 收盘后生成，非实时 · "
            "按行业与代码整理，序号不代表推荐优先级"
        ),
        title_size=24,
    )
    for index, (label, value) in enumerate(_light_overview(artifact)):
        x = 0.055 + index * 0.105
        fig.text(x, 0.811, label, color=MUTED, fontsize=6.8, fontproperties=cjk, va="top")
        fig.text(
            x,
            0.788,
            value,
            color=ACCENT_BLUE if label == "新增" else TEXT,
            fontsize=10.2,
            fontproperties=cjk_heavy,
            va="top",
        )
    fig.text(0.405, 0.811, "市场状态", color=MUTED, fontsize=6.8, fontproperties=cjk, va="top")
    fig.text(
        0.405,
        0.788,
        _truncate(_regime_summary(artifact.receipt), 42),
        color=TEXT,
        fontsize=9.3,
        fontproperties=cjk_heavy,
        va="top",
    )
    fig.add_artist(
        Line2D(
            [0.055, 0.95],
            [0.758, 0.758],
            transform=fig.transFigure,
            color=LINE,
            linewidth=0.75,
        )
    )


def _draw_light_share_bars(ax: Any, shares: Any, *, title: str) -> None:
    ordered = shares.sort_values(ascending=True)
    positions = range(len(ordered))
    maximum = float(ordered.max()) if not ordered.empty else 1.0
    ax.barh(positions, ordered.values, color=ACCENT_BLUE, alpha=0.82, height=0.42)
    ax.set_xlim(0, max(maximum * 1.32, 0.1))
    ax.set_xticks([])
    ax.set_yticks(
        list(positions),
        labels=[_truncate(label, 8) for label in ordered.index],
    )
    ax.tick_params(axis="y", length=0, colors=TEXT_SOFT, labelsize=6.7, pad=4)
    ax.set_title(title, loc="left", color=TEXT, fontsize=8.5, fontproperties=cjk_heavy, pad=5)
    for position, value in enumerate(ordered.values):
        ax.text(
            float(value) + maximum * 0.025,
            position,
            f"{float(value):.0%}",
            color=TEXT_SOFT,
            fontsize=6.7,
            va="center",
            fontproperties=cjk,
        )
    for label in ax.get_yticklabels():
        label.set_fontproperties(cjk)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _light_stock_row_copy(row: Any) -> tuple[str, str, str]:
    """Return compact row copy that preserves status, rationale, and risk."""
    classification = (
        f"{_truncate_display(row.get('industry'), 14)} · {_truncate_display(row.get('theme'), 14)}"
    )
    detail = (
        f"关注 {_short_tokens(row.get('top_drivers'), limit=2, width=18)} ｜ "
        f"风险 {_short_tokens(row.get('primary_risk'), limit=1, width=14)}"
    )
    status = "新增" if bool(row.get("is_new")) else "保留"
    return classification, _truncate_display(detail, 66), status


def _draw_light_stock_list(ax: Any, frame: Any) -> None:
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.plot([0.5, 0.5], [0, 1], color=LINE, linewidth=0.7)
    for index, row in enumerate(_records(frame)):
        column = 0 if index < 10 else 1
        row_index = index if index < 10 else index - 10
        x = 0.0 if column == 0 else 0.525
        row_right = x + 0.45
        y = 0.99 - row_index * 0.098
        classification, detail, status = _light_stock_row_copy(row)
        status_color = ACCENT_BLUE if status == "新增" else MUTED
        ax.text(
            x,
            y,
            f"{int(row['display_no']):02d}",
            color=TEXT,
            fontsize=9.2,
            fontproperties=cjk_heavy,
            va="top",
        )
        ax.text(
            x + 0.052,
            y,
            _truncate_display(row.get("name"), 14),
            color=TEXT,
            fontsize=9.2,
            fontproperties=cjk_heavy,
            va="top",
        )
        ax.text(
            x + 0.215,
            y - 0.003,
            str(row.get("symbol") or "-"),
            color=MUTED,
            fontsize=7.1,
            va="top",
        )
        ax.text(
            row_right,
            y,
            status,
            color=status_color,
            fontsize=8.2,
            fontproperties=cjk_heavy,
            ha="right",
            va="top",
        )
        ax.text(
            x + 0.052,
            y - 0.038,
            classification,
            color=MUTED,
            fontsize=6.8,
            fontproperties=cjk,
            va="top",
        )
        ax.text(
            x + 0.052,
            y - 0.068,
            detail,
            color=TEXT_SOFT,
            fontsize=6.2,
            fontproperties=cjk,
            va="top",
        )
        ax.plot([x, row_right], [y - 0.094, y - 0.094], color=LINE, linewidth=0.55)


def _draw_list_heading(fig: Any) -> None:
    fig.text(
        0.055,
        0.646,
        "20 只完整清单",
        color=TEXT,
        fontsize=9.2,
        fontproperties=cjk_heavy,
        va="top",
    )
    fig.text(
        0.95,
        0.646,
        "按行业与代码整理 · 序号不代表优先级",
        color=MUTED,
        fontsize=6.7,
        fontproperties=cjk,
        ha="right",
        va="top",
    )


def _draw_light_footer(fig: Any, artifact: DailyWatch20Artifact) -> None:
    warning = _client_candidate_data_warning(artifact.receipt)
    if warning:
        warning_lines = _wrap_display_text(warning, width=72, max_lines=2)
        fig.text(
            0.05,
            0.092,
            "\n".join(warning_lines),
            color=WARN,
            fontsize=7.1,
            fontproperties=cjk,
            va="top",
        )
    fig.text(
        0.05,
        0.054 if warning else 0.068,
        f"模型方法：{CLIENT_METHOD_SUMMARY}；日频与分钟输入须通过 freshness 门禁。",
        color=MUTED,
        fontsize=7.3,
        fontproperties=cjk,
        va="top",
    )
    fig.text(
        0.05,
        0.017 if warning else 0.025,
        CLIENT_DISCLAIMER,
        color=WARN,
        fontsize=8.2,
        fontweight="bold",
        fontproperties=cjk,
        va="top",
    )


def generate_daily_watch20_light_png(
    artifact: DailyWatch20Artifact,
    output_path: str | Path,
) -> Path:
    """Generate a light graph-paper DailyWatch20 sheet (PNG)."""
    frame = client_display_frame(artifact)
    _validate_client_frame_copy(artifact, frame)
    industries = _group_share(frame, "industry", limit=5)
    themes = _group_share(frame, "theme", limit=5)

    fig = plt.figure(figsize=(8, 10), facecolor=BG)
    apply_graph_paper(fig, LIGHT)
    ax_industry = fig.add_axes((0.105, 0.658, 0.36, 0.08), facecolor="none")
    ax_theme = fig.add_axes((0.585, 0.658, 0.365, 0.08), facecolor="none")
    ax_list = fig.add_axes((0.055, 0.12, 0.89, 0.50), facecolor="none")

    _draw_light_header(fig, artifact)
    _draw_light_share_bars(
        ax_industry,
        industries,
        title="行业分布",
    )
    _draw_light_share_bars(
        ax_theme,
        themes,
        title="主题分布",
    )
    _draw_list_heading(fig)
    _draw_light_stock_list(ax_list, frame)
    _draw_light_footer(fig, artifact)

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.stem}.tmp{output.suffix}")
    try:
        fig.savefig(tmp, dpi=160, facecolor=BG, edgecolor="none")
        tmp.replace(output)
    finally:
        plt.close(fig)
        tmp.unlink(missing_ok=True)
    return output


__all__ = ["generate_daily_watch20_light_png"]
