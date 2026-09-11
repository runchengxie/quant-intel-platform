"""Render canonical weekly basket artifacts for human review and Feishu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .report_theme import ReportTheme, get_report_theme
from .weekly_client_basket import BasketArtifact, _atomic_write, _csv_payload

SLEEVE_LABELS = {
    "dailywatch_family": "日内观察",
    "cashflow": "现金流因子",
    "microcap": "微盘股",
}

STATUS_LABELS = {"NEW": "新增", "KEEP": "保留", "DROP": "剔除"}


def _date_dash(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _cell(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def _status_symbols(artifact: BasketArtifact, status: str) -> str:
    positions = artifact.positions if status != "DROP" else artifact.trade_delta.dropped
    symbols = [position.symbol for position in positions if position.status == status]
    return "、".join(symbols) if symbols else "无"


def _performance_lines(performance: dict[str, Any] | None) -> list[str]:
    if not performance:
        return ["- 历史净值：暂无独立 performance.json，当前版本不展示回测曲线。"]
    series = performance.get("series", [])
    if not series:
        return [f"- 历史净值：{performance.get('status', 'unavailable')}。"]
    first = float(series[0]["nav"])
    last = float(series[-1]["nav"])
    change = (last / first - 1.0) * 100 if first else 0.0
    return [
        f"- 历史净值：{first:.3f} → {last:.3f}（累计 {change:+.2f}%）",
        f"- 曲线区间：{series[0]['date']} 至 {series[-1]['date']}；"
        f"来源方法：{performance.get('methodology', {}).get('method', '未说明')}。",
    ]


def render_basket_markdown(
    artifact: BasketArtifact,
    *,
    theme: str | ReportTheme = "research_editorial",
    performance: dict[str, Any] | None = None,
) -> str:
    """Render a deterministic Feishu-safe Markdown report."""
    selected_theme = get_report_theme(theme) if isinstance(theme, str) else theme
    shadow_present = any(position.research_only for position in artifact.positions)
    counts = {
        status: sum(position.status == status for position in artifact.positions)
        for status in ("NEW", "KEEP")
    }
    lines = [
        f"# 📌 周度组合 10 · Weekly Client Basket 10 · {_date_dash(artifact.report_date)}",
        "",
        f"> WEEKLY CLIENT BASKET · {selected_theme.label} · 周内默认冻结。",
        "",
        "## 本周组合",
        "",
        f"> {len(artifact.positions)} 只股票 · {counts['NEW']} 只新增 · {counts['KEEP']} 只保留",
        "",
    ]
    for index, position in enumerate(artifact.positions, start=1):
        lines.append(
            f"| {index} | {index:02d}｜**{_cell(position.name)}**（`{_cell(position.symbol)}`）｜"
            f"{SLEEVE_LABELS.get(position.source_strategy, position.source_strategy)}｜"
            f"{STATUS_LABELS.get(position.status, position.status)}（{position.status}）｜"
            f"信号 {_cell(_date_dash(position.signal_date))}｜Rank {_cell(position.rank)}"
        )
    lines.extend(
        [
            "",
            "## 交易差分",
            "",
            f"- 新增（NEW）：{_status_symbols(artifact, 'NEW')}",
            f"- 保留（KEEP）：{_status_symbols(artifact, 'KEEP')}",
            f"- 剔除（DROP）：{_status_symbols(artifact, 'DROP')}"
            f"（DROP: {_status_symbols(artifact, 'DROP')}）",
            "",
            "## 历史净值",
            "",
            *_performance_lines(performance),
            "",
            "## 说明",
            "",
            "- 现金流因子和微盘股若处于研究灰度（research shadow），会在来源字段中保留并标记。"
            if shadow_present
            else "- 当前组合来源均为正式有效 artifact。",
            "- 每只股票保留原始 signal_date、valid_until 和来源 artifact hash。",
            "- 非投资建议；请以实际可交易性和风控为准。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_basket_csv(artifact: BasketArtifact) -> str:
    return _csv_payload(artifact)


def write_rendered_outputs(
    artifact: BasketArtifact,
    output_dir: Path,
    *,
    theme: str | ReportTheme = "research_editorial",
    performance: dict[str, Any] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "report.md"
    csv_path = output_dir / "basket.csv"
    png_path = output_dir / "report.png"
    _atomic_write(
        markdown_path,
        render_basket_markdown(artifact, theme=theme, performance=performance).encode("utf-8"),
    )
    _atomic_write(csv_path, render_basket_csv(artifact).encode("utf-8"))
    from .weekly_client_basket_png import render_basket_png

    render_basket_png(artifact, png_path, theme=theme, performance=performance)
    return {"markdown": markdown_path, "csv": csv_path, "png": png_path}


__all__ = ["render_basket_csv", "render_basket_markdown", "write_rendered_outputs"]
