"""Render canonical weekly basket artifacts for human review and Feishu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .weekly_client_basket import BasketArtifact, _atomic_write, _csv_payload

SLEEVE_LABELS = {
    "dailywatch_family": "DailyWatch family",
    "cashflow": "Cashflow",
    "microcap": "Microcap",
}


def _date_dash(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _cell(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def _status_symbols(artifact: BasketArtifact, status: str) -> str:
    positions = artifact.positions if status != "DROP" else artifact.trade_delta.dropped
    symbols = [position.symbol for position in positions if position.status == status]
    return "、".join(symbols) if symbols else "无"


def render_basket_markdown(artifact: BasketArtifact) -> str:
    """Render a deterministic Feishu-safe Markdown report."""
    shadow_present = any(position.research_only for position in artifact.positions)
    lines = [
        f"# 📌 Weekly Client Basket 10 · {_date_dash(artifact.report_date)}",
        "",
        "> 周度 snapshot；周内默认冻结。",
        "",
        "## 本周组合",
        "",
        "| # | 股票 | 来源 | 状态 | 信号日期 | 有效至 | Rank | Score |",
        "| ---: | --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for index, position in enumerate(artifact.positions, start=1):
        lines.append(
            "| "
            + " | ".join(
                (
                    str(index),
                    f"{_cell(position.name)}（{_cell(position.symbol)}）",
                    _cell(SLEEVE_LABELS.get(position.source_strategy, position.source_strategy)),
                    _cell(position.status),
                    _cell(_date_dash(position.signal_date)),
                    _cell(_date_dash(position.valid_until) if position.valid_until else None),
                    _cell(position.rank),
                    _cell(position.score),
                )
            )
            + "|"
        )
    lines.extend(
        [
            "",
            "## 交易差分",
            "",
            f"- NEW: {_status_symbols(artifact, 'NEW')}",
            f"- KEEP: {_status_symbols(artifact, 'KEEP')}",
            f"- DROP: {_status_symbols(artifact, 'DROP')}",
            "",
            "## 说明",
            "",
            "- Cashflow 和 Microcap 若处于 research shadow，会在来源字段中保留并标记。"
            if shadow_present
            else "- 当前组合来源均为正式有效 artifact。",
            "- 每只股票保留原始 signal_date、valid_until 和来源 artifact hash。",
            "- 非投资建议；请以实际可交易性和风控为准。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_basket_csv(artifact: BasketArtifact) -> str:
    return _csv_payload(artifact)


def write_rendered_outputs(artifact: BasketArtifact, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "report.md"
    csv_path = output_dir / "basket.csv"
    _atomic_write(markdown_path, render_basket_markdown(artifact).encode("utf-8"))
    _atomic_write(csv_path, render_basket_csv(artifact).encode("utf-8"))
    return {"markdown": markdown_path, "csv": csv_path}


__all__ = ["render_basket_csv", "render_basket_markdown", "write_rendered_outputs"]
