"""Feishu-safe Markdown renderer for ReportDocument."""

from __future__ import annotations

from .model import ReportDocument
from .themes import ReportTheme


def render_markdown(document: ReportDocument, theme: ReportTheme) -> str:
    lines = [
        f"# {document.title}",
        "",
        f"> {document.report_type} · {document.report_date} · {theme.name}",
        "",
    ]
    for group in document.metrics:
        lines.extend([f"## {group.title}", ""])
        lines.extend(f"- {metric.label}：{metric.value}{metric.unit}" for metric in group.metrics)
        lines.append("")
    for section in document.sections:
        lines.extend([f"## {section.title}", ""])
        for group in section.metrics:
            lines.extend(
                f"- {metric.label}：{metric.value}{metric.unit}" for metric in group.metrics
            )
        for position in section.positions:
            lines.append(f"- `{position.symbol}` {position.name} · {position.status}")
        lines.append("")
    if document.notices:
        lines.extend(["## 说明", ""])
        lines.extend(f"- {notice.text}" for notice in document.notices)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_markdown"]
