"""Markdown renderer for validated daily report artifacts."""

from __future__ import annotations

import re

from ops_common.locale import normalize_locale

from .models import DailyReport, ReportSection

_SECTION_TITLES = {
    "en-US": {
        "market": "Market performance",
        "equities": "U.S. equities and key names",
        "cross_asset": "Cross-asset markets",
        "drivers": "Market drivers",
        "macro": "Macro data and Federal Reserve",
        "company_news": "Company news",
        "movers": "Top gainers and losers",
    },
    "zh-CN": {
        "market": "市场表现",
        "equities": "美股核心观察与重点个股行情",
        "cross_asset": "跨资产行情",
        "drivers": "市场驱动因素",
        "macro": "经济数据与美联储动态",
        "company_news": "公司新闻",
        "movers": "主要上涨与下跌个股",
    },
}

_COPY = {
    "en-US": {
        "title": "Market report",
        "status": "Data status",
        "cutoff": "Evidence cutoff",
        "observation_date": "observation date",
        "source": "source",
        "empty": "No validated content.",
        "gaps": "Data gaps",
    },
    "zh-CN": {
        "title": "市场日报",
        "status": "数据状态",
        "cutoff": "资料核实截至",
        "observation_date": "观测日",
        "source": "来源",
        "empty": "暂无已校验内容。",
        "gaps": "数据缺口",
    },
}


def render_markdown(report: DailyReport, *, locale: str | None = None) -> str:
    normalized_locale = normalize_locale(locale)
    copy = _COPY[normalized_locale]
    section_titles = _SECTION_TITLES[normalized_locale]
    report_date = (
        report.run_id.removeprefix("daily-")
        if re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", report.run_id)
        else report.as_of.date().isoformat()
    )
    lines = [
        f"# {copy['title']} ({report_date})"
        if normalized_locale == "en-US"
        else f"# {copy['title']}（{report_date}）",
        "",
        f"{copy['status']}: {report.quality_summary.get('status', 'unknown')}",
        f"{copy['cutoff']}: {report.as_of.isoformat()}",
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
        section_title = section_titles.get(section.key, section.title)
        lines.extend([f"## {section_title}", ""])
        if section.facts:
            for fact_id in section.facts:
                fact = facts_by_id.get(fact_id)
                if fact is None:
                    continue
                observation = (
                    f"; {copy['observation_date']} {fact.observation_date}"
                    if normalized_locale == "en-US" and fact.observation_date
                    else f"；{copy['observation_date']} {fact.observation_date}"
                    if fact.observation_date
                    else ""
                )
                source = (
                    f"; [{copy['source']}]({fact.source_url})"
                    if normalized_locale == "en-US"
                    and fact.source_url
                    and fact.source_url.startswith("https://")
                    else f"；[{copy['source']}]({fact.source_url})"
                    if fact.source_url and fact.source_url.startswith("https://")
                    else ""
                )
                if normalized_locale == "en-US":
                    lines.append(
                        f"- {fact.instrument or fact.metric}: {fact.value} {fact.unit or ''} "
                        f"({fact.source}{observation}{source})"
                    )
                else:
                    lines.append(
                        f"- {fact.instrument or fact.metric}：{fact.value} {fact.unit or ''}"
                        f"（{fact.source}{observation}{source}）"
                    )
        if section.claims:
            for claim_id in section.claims:
                claim = claims_by_evidence.get(claim_id)
                if claim:
                    source = (
                        f" ([{copy['source']}]({claim.sources[0]}))"
                        if normalized_locale == "en-US"
                        and claim.sources
                        and claim.sources[0].startswith("https://")
                        else f"（[{copy['source']}]({claim.sources[0]})）"
                        if claim.sources and claim.sources[0].startswith("https://")
                        else ""
                    )
                    lines.append(f"- {claim.claim}{source}")
        if not section.facts and not section.claims:
            lines.append(copy["empty"])
        lines.append("")
    if report.missing_sources:
        lines.extend(
            [f"## {copy['gaps']}", "", *[f"- {source}" for source in report.missing_sources], ""]
        )
    return "\n".join(lines)
