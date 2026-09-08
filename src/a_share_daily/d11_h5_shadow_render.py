"""PNG rendering for the D11-H5 research-only target."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from textwrap import wrap
from typing import Any

import matplotlib

matplotlib.use("Agg")

from .charts.theme import (
    ACCENT,
    BG,
    DOWN,
    FG,
    LINE,
    MUTED,
    UP,
    add_report_header,
    apply_editorial_background,
    cjk,
    cjk_heavy,
)


def _draw_position_row(ax: Any, row: Mapping[str, Any], index: int) -> None:
    column = 0 if index < 10 else 1
    row_index = index if index < 10 else index - 10
    x = 0.0 if column == 0 else 0.52
    y = 0.865 - row_index * 0.054
    status, rank_text = _position_row_copy(row)
    is_new = status == "新增"
    status_color = ACCENT if is_new else MUTED
    common: dict[str, Any] = {"fontproperties": cjk, "va": "top"}
    ax.text(
        x,
        y,
        str(index + 1),
        color=FG,
        fontsize=9.2,
        fontproperties=cjk_heavy,
        va="top",
    )
    ax.text(
        x + 0.052,
        y,
        str(row.get("name")),
        color=FG,
        fontsize=9.2,
        fontproperties=cjk_heavy,
        va="top",
    )
    ax.text(
        x + 0.205,
        y - 0.002,
        str(row.get("symbol") or "-"),
        color=MUTED,
        fontsize=7.7,
        **common,
    )
    ax.text(
        x + 0.465,
        y,
        f"{status}{rank_text}",
        color=status_color,
        fontsize=8.3,
        ha="right",
        **common,
    )
    ax.plot([x, x + 0.465], [y - 0.038, y - 0.038], color=LINE, linewidth=0.45)


def _position_row_copy(row: Mapping[str, Any]) -> tuple[str, str]:
    """Normalize client-facing status language while retaining refreshed rank context."""
    status = "新增" if bool(row.get("is_new")) else "保留"
    model_rank = row.get("model_rank") if bool(row.get("is_refreshed", True)) else None
    rank_text = f" · #{int(model_rank)}" if model_rank is not None else ""
    return status, rank_text


def _compact_change_text(prefix: str, rows: Sequence[Mapping[str, Any]], *, width: int = 16) -> str:
    """Render rotation names within the change-panel width.

    Matplotlib's ``Text(wrap=True)`` does not reliably wrap against an axes
    width when exporting a PNG. Explicitly wrapping here keeps long rotation
    lists from colliding with the next section or running off the canvas.
    """
    names = "、".join(str(row.get("name")) for row in rows) or "无"
    name_width = max(width - len(prefix) - 1, 4)
    lines = wrap(
        names.replace("、", "、 "),
        width=name_width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    lines = [line.replace(" ", "") for line in lines]
    return f"{prefix}：" + "\n".join(lines[:2])


def _draw_positions(ax: Any, positions: Sequence[Mapping[str, Any]], *, is_v2: bool) -> None:
    common: dict[str, Any] = {"fontproperties": cjk}
    ax.text(
        0,
        0.915,
        "当前完整组合 · 20 只等权 · 单股 5%" if is_v2 else "本次更新子组合 · 每只约占总组合 1%",
        color=FG,
        fontsize=12,
        fontweight="bold",
        va="top",
        **common,
    )
    ax.plot([0.49, 0.49], [0.355, 0.89], color=LINE, linewidth=0.65)
    for index, row in enumerate(positions):
        _draw_position_row(ax, row, index)


def _draw_changes(
    ax: Any,
    added: Sequence[Mapping[str, Any]],
    removed: Sequence[Mapping[str, Any]],
    *,
    is_v2: bool,
) -> None:
    common: dict[str, Any] = {"fontproperties": cjk}
    ax.plot([0, 1], [0.325, 0.325], color=LINE, linewidth=0.9)
    added_text = _compact_change_text("新增", added)
    removed_text = _compact_change_text("移除", removed)
    ax.text(0, 0.292, "轮换变化", color=FG, fontsize=11.5, fontweight="bold", **common)
    ax.text(0, 0.248, added_text, color=DOWN, fontsize=8.8, **common)
    ax.text(0, 0.188, removed_text, color=UP, fontsize=8.8, **common)
    hint = (
        "阅读提示：完整组合固定 20 只；今日仅更新其中一个 4 股子组合"
        if is_v2
        else "阅读提示：今日 20 只来自本次更新子组合，完整目标由五个子组合合并"
    )
    ax.text(0, 0.095, hint, color=MUTED, fontsize=8.8, **common)
    ax.text(
        0,
        0.055,
        "完整方法与研究口径见随附飞书文档",
        color=MUTED,
        fontsize=8.2,
        **common,
    )


def render_png(artifact: Mapping[str, Any], output_path: Path) -> Path:
    import matplotlib.pyplot as plt

    from .d11_h5_shadow_delivery import _date_dash, _is_v2, _mapping, _png_positions, _rows

    signal = _mapping(artifact["signal"], label="selection.signal")
    aggregate = _mapping(artifact["aggregate_target"], label="selection.aggregate_target")
    positions = _png_positions(artifact)
    added = _rows(signal.get("added", []), label="selection.signal.added")
    removed = _rows(signal.get("removed", []), label="selection.signal.removed")
    is_v2 = _is_v2(artifact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # The content is a fixed two-column sheet; a shorter canvas keeps the
    # change notes and reading hint from floating in an oversized lower area.
    fig = plt.figure(figsize=(10.8, 10.8), facecolor=BG)
    apply_editorial_background(fig)
    add_report_header(
        fig,
        kicker=f"{_date_dash(artifact['signal_date'])} · D11–H5 / MEDIUM-HORIZON ROTATION",
        title="中期排序五日错峰",
        subtitle=(
            f"每日关注清单 · {_date_dash(artifact['source_date'])} 收盘信号 → "
            f"{_date_dash(artifact['signal_date'])} 开盘目标"
        ),
        title_size=25,
    )
    ax = fig.add_axes((0.055, 0.035, 0.89, 0.77), facecolor="none")
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    metrics = (
        (0.0, f"轮换 {signal['cohort_number']} / 5", FG),
        (
            0.25,
            f"新增 {signal['new_position_count']} · 移除 {signal['exited_count']}",
            ACCENT,
        ),
        (0.58, f"完整组合 {aggregate['unique_position_count']} 只", FG),
    )
    for x, text, color in metrics:
        ax.text(
            x,
            0.985,
            text,
            color=color,
            fontsize=11.8,
            va="top",
            fontproperties=cjk_heavy,
        )
    ax.plot([0, 1], [0.945, 0.945], color=LINE, linewidth=0.9)
    _draw_positions(ax, positions, is_v2=is_v2)
    _draw_changes(ax, added, removed, is_v2=is_v2)
    temporary = output_path.with_name(f".{output_path.stem}.{os.getpid()}.tmp.png")
    try:
        fig.savefig(temporary, dpi=150, facecolor=BG, edgecolor="none")
        temporary.replace(output_path)
    finally:
        plt.close(fig)
        temporary.unlink(missing_ok=True)
    return output_path
