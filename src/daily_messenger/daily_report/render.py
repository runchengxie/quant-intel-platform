"""Markdown renderer for validated daily report artifacts."""

from __future__ import annotations

import re

from .models import DailyReport, ReportSection


def render_markdown(report: DailyReport) -> str:
    report_date = (
        report.run_id.removeprefix("daily-")
        if re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", report.run_id)
        else report.as_of.date().isoformat()
    )
    lines = [
        f"# 市场日报（{report_date}）",
        "",
        f"数据状态：{report.quality_summary.get('status', 'unknown')}",
        f"资料核实截至：{report.as_of.isoformat()}",
        "",
    ]
    claims_by_evidence = {
        evidence_id: claim for claim in report.claims for evidence_id in claim.evidence_ids
    }
    facts_by_id = {fact.id: fact for fact in report.facts}
    sections = report.sections or tuple(
        ReportSection(key=key, title=title)
        for key, title in (("market", "市场表现"), ("drivers", "市场驱动因素"))
    )
    for section in sections:
        lines.extend([f"## {section.title}", ""])
        if section.facts:
            for fact_id in section.facts:
                fact = facts_by_id.get(fact_id)
                if fact is None:
                    continue
                observation = f"；观测日 {fact.observation_date}" if fact.observation_date else ""
                source = (
                    f"；[来源]({fact.source_url})"
                    if fact.source_url and fact.source_url.startswith("https://")
                    else ""
                )
                lines.append(
                    f"- {fact.instrument or fact.metric}：{fact.value} {fact.unit or ''}"
                    f"（{fact.source}{observation}{source}）"
                )
        if section.claims:
            for claim_id in section.claims:
                claim = claims_by_evidence.get(claim_id)
                if claim:
                    source = (
                        f"（[来源]({claim.sources[0]})）"
                        if claim.sources and claim.sources[0].startswith("https://")
                        else ""
                    )
                    lines.append(f"- {claim.claim}{source}")
        if not section.facts and not section.claims:
            lines.append("暂无已校验内容。")
        lines.append("")
    if report.missing_sources:
        lines.extend(["## 数据缺口", "", *[f"- {source}" for source in report.missing_sources], ""])
    return "\n".join(lines)
