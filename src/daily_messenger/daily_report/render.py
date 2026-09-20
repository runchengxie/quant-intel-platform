"""Markdown renderer for validated daily report artifacts."""

from __future__ import annotations

from .models import DailyReport, ReportSection


def render_markdown(report: DailyReport) -> str:
    lines = [
        f"# 市场日报（{report.as_of.date().isoformat()}）",
        "",
        f"数据状态：{report.quality_summary.get('status', 'unknown')}",
        "",
    ]
    sections = report.sections or tuple(
        ReportSection(key=key, title=title)
        for key, title in (("market", "市场表现"), ("drivers", "市场驱动因素"))
    )
    for section in sections:
        lines.extend([f"## {section.title}", ""])
        if section.facts:
            lines.extend(f"- `{fact_id}`" for fact_id in section.facts)
        elif section.claims:
            lines.extend(f"- {claim_id}" for claim_id in section.claims)
        else:
            lines.append("暂无已校验内容。")
        lines.append("")
    if report.missing_sources:
        lines.extend(["## 数据缺口", "", *[f"- {source}" for source in report.missing_sources], ""])
    return "\n".join(lines)
