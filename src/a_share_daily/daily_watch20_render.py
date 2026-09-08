"""HTML, PNG, and Markdown delivery renderers for DailyWatch20 artifacts."""

from __future__ import annotations

from pathlib import Path

from .daily_watch20 import (
    DailyWatch20Artifact,
    DailyWatch20RenderResult,
    _atomic_write_text,
    _date_dash,
    _draw_distribution,
    _draw_note_panel,
    _draw_summary_header,
    _draw_table,
    _group_weights,
    _minute_summary,
    _records,
    _regime_summary,
    _top_text_items,
    build_daily_watch20_html,
)
from .daily_watch20_client_render import (
    generate_daily_watch20_client_png,
    render_daily_watch20_client_markdown,
)
from .daily_watch20_light_render import generate_daily_watch20_light_png


def _validate_audience(audience: str) -> str:
    if audience not in {"client", "internal"}:
        raise ValueError("DailyWatch20 audience must be 'client' or 'internal'.")
    return audience


def generate_daily_watch20_png(
    artifact: DailyWatch20Artifact,
    output_path: str | Path,
    *,
    audience: str = "client",
    theme: str = "light",
) -> Path:
    audience = _validate_audience(audience)
    if audience == "client":
        if theme == "light":
            return generate_daily_watch20_light_png(artifact, output_path)

        return generate_daily_watch20_client_png(artifact, output_path)

    import matplotlib.pyplot as plt

    from a_share_daily.charts.theme import (
        ACCENT,
        BG,
        DOWN,
        MUTED,
        YELLOW,
        apply_editorial_background,
        cjk,
    )

    fig = plt.figure(figsize=(14, 17), facecolor=BG)
    apply_editorial_background(fig)
    grid = fig.add_gridspec(
        5,
        2,
        left=0.08,
        right=0.965,
        top=0.755,
        bottom=0.045,
        height_ratios=(2.1, 1.35, 4.9, 1.0, 0.2),
        hspace=0.31,
        wspace=0.22,
    )
    _draw_summary_header(fig, artifact, font=cjk)
    ax_industry = fig.add_subplot(grid[0, 0])
    ax_theme = fig.add_subplot(grid[0, 1])
    _draw_distribution(ax_industry, ax_theme, artifact, cjk)
    ax_a = fig.add_subplot(grid[1, :])
    _draw_table(ax_a, artifact.a_frame, title="A4 · 模型探索", color=DOWN, font=cjk)
    ax_b = fig.add_subplot(grid[2, :])
    _draw_table(ax_b, artifact.b_frame, title="B16 · 约束观察", color=ACCENT, font=cjk)
    ax_drivers = fig.add_subplot(grid[3, 0])
    ax_risks = fig.add_subplot(grid[3, 1])
    _draw_note_panel(
        ax_drivers,
        "主要驱动",
        _top_text_items(artifact.frame, "top_drivers"),
        color=DOWN,
        font=cjk,
    )
    _draw_note_panel(
        ax_risks,
        "主要风险",
        _top_text_items(artifact.frame, "primary_risk"),
        color=YELLOW,
        font=cjk,
    )
    ax_footer = fig.add_subplot(grid[4, :], facecolor=BG)
    ax_footer.axis("off")
    ax_footer.text(
        0,
        0.55,
        f"{_minute_summary(artifact.receipt)} · 纯 artifact 展示层，不重新打分或选股 · 仅供研究观察",
        fontsize=8,
        color=MUTED,
        fontproperties=cjk,
    )
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.stem}.tmp{output.suffix}")
    try:
        fig.savefig(tmp, dpi=150, facecolor=BG, edgecolor="none")
        tmp.replace(output)
    finally:
        plt.close(fig)
        tmp.unlink(missing_ok=True)
    return output


def render_daily_watch20(
    artifact: DailyWatch20Artifact,
    output_dir: str | Path,
    *,
    audience: str = "client",
    theme: str = "light",
) -> DailyWatch20RenderResult:
    audience = _validate_audience(audience)
    resolved = Path(output_dir).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    html_path = resolved / "daily_watch20.html"
    png_path = resolved / "daily_watch20.png"
    _atomic_write_text(html_path, build_daily_watch20_html(artifact, audience=audience))
    generate_daily_watch20_png(artifact, png_path, audience=audience, theme=theme)
    return DailyWatch20RenderResult(artifact=artifact, html_path=html_path, png_path=png_path)


def render_daily_watch20_markdown(
    artifact: DailyWatch20Artifact,
    *,
    strategy_doc_url: str | None = None,
    audience: str = "client",
) -> str:
    audience = _validate_audience(audience)
    if audience == "client":
        return render_daily_watch20_client_markdown(
            artifact,
            strategy_doc_url=strategy_doc_url,
        )

    industry = _group_weights(artifact.frame, "industry").head(3)
    themes = _group_weights(artifact.frame, "theme").head(3)
    drivers = _top_text_items(artifact.frame, "top_drivers", limit=4)
    risks = _top_text_items(artifact.frame, "primary_risk", limit=4)

    frame = artifact.frame.sort_values(
        ["final_score", "symbol"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)
    frame["global_rank"] = range(1, len(frame) + 1)

    lines = [
        f"# [内部审计] 今日20只重点关注（{_date_dash(artifact.signal_date)}）",
        "",
        f"正式 DailyWatch20 artifact · 源数据 {_date_dash(artifact.source_date)}",
        f"A4 / B16 · model={artifact.receipt.get('model_version')} · feature_set={artifact.receipt.get('feature_set_id')}",
        "",
    ]
    for row in _records(frame):
        lines.append(
            f"{int(row['global_rank'])}. {row['symbol']} {row['name']}"
            f"｜{row['industry'] or '未分类'}｜{float(row['tracking_weight']):.1%}"
        )
    lines.extend(
        [
            "",
            "## 结构摘要",
            "- 行业 Top：" + "、".join(f"{name} {value:.1%}" for name, value in industry.items()),
            "- 主题 Top：" + "、".join(f"{name} {value:.1%}" for name, value in themes.items()),
            "- 主要驱动：" + ("；".join(drivers) if drivers else "artifact 未提供"),
            "- 主要风险：" + ("；".join(risks) if risks else "artifact 未提供"),
            "- 市场状态：" + _regime_summary(artifact.receipt),
        ]
    )
    if strategy_doc_url:
        lines.extend(["", f"📖 查看完整方法：[每日20股关注清单方法说明]({strategy_doc_url})"])
    lines.extend(["", "仅供研究观察，不构成投资建议。"])
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "generate_daily_watch20_png",
    "render_daily_watch20",
    "render_daily_watch20_markdown",
]
