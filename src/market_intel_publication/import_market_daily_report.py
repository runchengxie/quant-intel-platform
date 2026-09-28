"""Import a validated platform daily report into the public Pages tree."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .us_daily_contract import (
    ASSET_GAP_LABELS,
    EQUITY_ID,
    FACT_LABELS,
    MISSING_LABELS,
    RESEARCH_SECTION_TITLES,
    SOURCE_QUALITY_LABELS,
    SOURCE_REASON_LABELS,
    SOURCE_STATUS_LABELS,
    _date,
    _public_manifest,
    _public_payload,
    _read,
    _valid_market_fact,
)
from .us_daily_contract import (
    _normalize as _normalize,
)


def _missing_labels(payload: dict[str, Any]) -> list[str]:
    labels = []
    facts = {str(fact.get("id")) for fact in payload.get("facts", [])}
    for item in payload.get("missing_sources", []):
        if item == "cross_asset":
            unavailable = [
                name
                for asset, name in ASSET_GAP_LABELS.items()
                if f"cross_asset.{asset}.close" not in facts
                or f"cross_asset.{asset}.change_percent" not in facts
            ]
            labels.extend(unavailable or [MISSING_LABELS[item]])
        elif item in MISSING_LABELS:
            labels.append(MISSING_LABELS[item])
    return labels


def _fact_category(fact_id: str) -> str:
    for prefix, category in (
        ("index.", "market"),
        ("equity.", "equities"),
        ("treasury.", "rates"),
        ("cross_asset.", "cross_asset"),
        ("macro.", "macro"),
    ):
        if fact_id.startswith(prefix):
            return category
    return ""


def _markdown_source(fact: dict[str, Any]) -> str:
    fact_id = str(fact["id"])
    url = str(fact["source_url"])
    if fact_id.startswith("index."):
        name = "Yahoo Finance" if fact.get("source") == "Yahoo Finance" else "核实报道"
    elif fact_id.startswith("equity."):
        name = str(fact.get("source"))
    elif fact_id.startswith("cross_asset."):
        name = {
            "Financial Modeling Prep": "FMP",
            "Data provided by CoinGecko": "Data provided by CoinGecko",
            "Kraken": "Kraken",
        }.get(fact.get("source"), "Yahoo Finance")
    elif url.startswith("https://home.treasury.gov/"):
        name = "美国财政部"
    else:
        name = "FRED"
    return f"[{name}]({url})"


def _market_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 指数 | 收盘涨跌 | 观测日 | 来源 |", "|---|---:|---|---|"]
        if include_references
        else ["| 指数 | 收盘涨跌 | 观测日 |", "|---|---:|---|"]
    )
    for fact in facts:
        label = FACT_LABELS[fact["id"]][0].removesuffix("日涨跌").strip()
        lines.append(
            f"| {label} | {float(fact['value']):+.2f}% | {fact['observation_date']} |"
            + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _equities_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 股票 | 收盘价 | 日涨跌 | 观测日 | 来源 |", "|---|---:|---:|---|---|"]
        if include_references
        else ["| 股票 | 收盘价 | 日涨跌 | 观测日 |", "|---|---:|---:|---|"]
    )
    by_id = {fact["id"]: fact for fact in facts}
    for fact in facts:
        match = EQUITY_ID.fullmatch(fact["id"])
        if not match or match.group(2) != "close":
            continue
        change = by_id[f"equity.{match.group(1)}.change_percent"]
        lines.append(
            f"| {fact['instrument']} | {float(fact['value']):,.2f} 美元 | "
            f"{float(change['value']):+.2f}% | {fact['observation_date']} |"
            + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _rates_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 美债期限 | 收益率水平 | 日变动 | 观测日 | 来源 |", "|---|---:|---:|---|---|"]
        if include_references
        else ["| 美债期限 | 收益率水平 | 日变动 | 观测日 |", "|---|---:|---:|---|"]
    )
    names = {"2y": "2 年期", "5y": "5 年期", "10y": "10 年期", "30y": "30 年期"}
    by_id = {fact["id"]: fact for fact in facts}
    for tenor, name in names.items():
        level = by_id.get(f"treasury.{tenor}.level_percent")
        change = by_id.get(f"treasury.{tenor}.change_bp")
        if not level and not change:
            continue
        level_text = f"{float(level['value']):.2f}%" if level else "—"
        change_text = f"{float(change['value']):+.2f} bp" if change else "—"
        fact = change if change is not None else level
        if fact is None:
            continue
        lines.append(
            f"| {name} | {level_text} | {change_text} | "
            f"{fact['observation_date']} |"
            + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _cross_asset_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 品种 | 价格 | 日涨跌 | 观测日 | 来源 |", "|---|---:|---:|---|---|"]
        if include_references
        else ["| 品种 | 价格 | 日涨跌 | 观测日 |", "|---|---:|---:|---|"]
    )
    for fact in facts:
        if not fact["id"].endswith(".close"):
            continue
        _, asset, _ = fact["id"].split(".")
        change = next(
            (row for row in facts if row["id"] == f"cross_asset.{asset}.change_percent"), None
        )
        if change is None:
            continue
        label = FACT_LABELS[fact["id"]][0].removesuffix("收盘")
        unit = FACT_LABELS[fact["id"]][1]
        lines.append(
            f"| {label} | {float(fact['value']):,.2f} {unit} | {float(change['value']):+.2f}% | "
            f"{fact['observation_date']} |"
            + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _macro_table(facts: list[dict[str, Any]], include_references: bool = True) -> list[str]:
    lines = (
        ["| 数据 | 数值 | 观测日 | 来源 |", "|---|---:|---|---|"]
        if include_references
        else ["| 数据 | 数值 | 观测日 |", "|---|---:|---|"]
    )
    for fact in facts:
        label, unit = FACT_LABELS[fact["id"]]
        lines.append(
            f"| {label} | {float(fact['value']):.2f}{unit} | {fact['observation_date']} |"
            + (f" {_markdown_source(fact)} |" if include_references else "")
        )
    return lines


def _markdown_fact_lines(
    payload: dict[str, Any],
    section: str,
    include_references: bool = True,
    *,
    allow_legacy_commodity: bool = False,
) -> list[str]:
    grouped = []
    for fact in payload["facts"]:
        fact_id = str(fact.get("id") or "")
        if _fact_category(fact_id) != section or (
            fact_id not in FACT_LABELS and not EQUITY_ID.fullmatch(fact_id)
        ):
            continue
        value = fact.get("value")
        observed = str(fact.get("observation_date") or "")
        is_valid = (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", observed)
            and _valid_market_fact(
                fact, _date(payload), allow_legacy_commodity=allow_legacy_commodity
            )
        )
        if not is_valid:
            raise ValueError(f"invalid sourced market fact: {fact_id}")
        grouped.append(fact)
    if not grouped:
        return []
    renderers = {
        "market": _market_table,
        "equities": _equities_table,
        "rates": _rates_table,
        "cross_asset": _cross_asset_table,
        "macro": _macro_table,
    }
    return renderers[section](grouped, include_references)


def _source_status_lines(statuses: dict[str, Any], include_references: bool = True) -> list[str]:
    if not statuses:
        return []
    lines = ["## 数据质量与核验说明", "", "| 数据链路 | 状态 | 说明 |", "|---|---|---|"]
    for key, label in SOURCE_STATUS_LABELS.items():
        status = statuses.get(key)
        if not isinstance(status, dict):
            continue
        quality = SOURCE_QUALITY_LABELS.get(status.get("quality"), "未确认")
        reason = SOURCE_REASON_LABELS.get(status.get("reason"), "详见逐项观测日与来源")
        lines.append(f"| {label} | {quality} | {reason} |")
    return (
        [*lines, "", "证据编号对应已审阅材料；公开报告不包含私有核验工作底稿。", ""]
        if include_references
        else [*lines, ""]
    )


def _claim_markdown_lines(claim: dict[str, Any], include_references: bool) -> list[str]:
    lines = [f"- {claim['claim']}"]
    if include_references:
        evidence = ", ".join(f"`{item}`" for item in claim["evidence_ids"])
        sources = "、".join(
            f"[来源{index}]({url})" for index, url in enumerate(claim["sources"], start=1)
        )
        lines.extend([f"  - 证据：{evidence}", f"  - {sources}"])
    return lines


def _markdown_header(payload: dict[str, Any], include_references: bool) -> list[str]:
    lines = [f"# 美股市场日报（{_date(payload)}）", ""]
    if include_references:
        lines.extend(
            [
                f"数据状态：{payload.get('quality_summary', {}).get('status', 'unknown')}",
                f"报告生成时间：{payload['as_of']}（美东报告日 {_date(payload)}）",
                "",
            ]
        )
        cutoff = payload.get("quality_summary", {}).get("reviewed_source_cutoff")
        if cutoff:
            lines.extend([f"新闻资料截止：{cutoff}。", ""])
    if payload.get("quality_summary", {}).get("revision") == "historical_backfill":
        lines.extend(
            [
                "历史补报：按指定交易日数据事后重建，生成时间不代表当日已发布。"
                if include_references
                else "事后整理",
                "",
            ]
        )
    return lines


def _markdown(
    payload: dict[str, Any],
    include_references: bool = True,
    *,
    allow_legacy_commodity: bool = False,
) -> str:
    lines = _markdown_header(payload, include_references)
    gaps = _missing_labels(payload)
    if gaps:
        lines.extend([f"尚缺：{'、'.join(gaps)}。", ""])
    grouped = _group_claims(payload)
    report_sections = (
        ("market", "美股市场表现"),
        ("equities", "美股个股行情"),
        ("movers", "主要个股"),
        ("rates", "美债收益率"),
        ("cross_asset", "布伦特、金银与比特币"),
        ("drivers", "市场驱动因素"),
        ("macro", "经济数据与美联储动态"),
        ("company_news", "公司新闻"),
    )
    for key, title in report_sections:
        lines.extend([f"## {title}", ""])
        facts = _markdown_fact_lines(
            payload, key, include_references, allow_legacy_commodity=allow_legacy_commodity
        )
        lines.extend(facts)
        for claim in grouped.get(key, []):
            lines.extend(_claim_markdown_lines(claim, include_references))
        if not facts and not grouped.get(key, []):
            lines.append("暂无经核实内容。")
        lines.append("")
    if grouped["other"]:
        lines.extend(["## 其他已核实内容", ""])
        for claim in grouped["other"]:
            lines.extend(_claim_markdown_lines(claim, include_references))
    source_status = (
        _source_status_lines(payload.get("source_status", {}), include_references)
        if include_references
        else []
    )
    lines.extend(source_status)
    if not source_status:
        lines.append("")
    return "\n".join(lines)


def _text_fact_lines(payload: dict[str, Any], prefix: str) -> list[str]:
    facts = {fact["id"]: fact for fact in payload["facts"] if fact.get("id") in FACT_LABELS}
    lines = []
    for fact_id, (label, unit) in FACT_LABELS.items():
        if not fact_id.startswith(prefix) or fact_id not in facts:
            continue
        fact = facts[fact_id]
        signed = fact_id.startswith("index.") or fact_id.endswith((".change_bp", ".change_percent"))
        value = f"{fact['value']:+.2f}" if signed else f"{fact['value']:.2f}"
        suffix = unit if unit == "%" else f" {unit}"
        lines.extend(
            [
                f"- {label}：{value}{suffix}（观测日 {fact['observation_date']}）",
                f"  来源：{fact['source_url']}",
            ]
        )
    return lines


def _group_claims(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in RESEARCH_SECTION_TITLES}
    groups["other"] = []
    section_ids = {
        section.get("key"): set(section.get("claims", []))
        for section in payload.get("sections", [])
        if isinstance(section, dict) and isinstance(section.get("claims"), list)
    }
    for claim in payload["claims"]:
        key = next(
            (
                key
                for key in RESEARCH_SECTION_TITLES
                if section_ids.get(key, set()).intersection(claim["evidence_ids"])
            ),
            "other",
        )
        groups[key].append(claim)
    return groups


def _text_claim_lines(claims: list[dict[str, Any]]) -> list[str]:
    if not claims:
        return ["- 暂无经核实内容。"]
    lines = []
    for index, claim in enumerate(claims, start=1):
        lines.extend(
            [f"{index}、{claim['claim']}", *(f"   来源：{url}" for url in claim["sources"])]
        )
    return lines


def _text_report(payload: dict[str, Any]) -> str:
    report_date = _date(payload)
    grouped = _group_claims(payload)
    market_facts = _text_fact_lines(payload, "index.")
    equity_facts = [
        f"- {fact['instrument']}：{float(fact['value']):,.2f} 美元，"
        f"{float(next(row for row in payload['facts'] if row['id'] == fact['id'].removesuffix('.close') + '.change_percent')['value']):+.2f}%"
        f"（观测日 {fact['observation_date']}）\n  来源：{fact['source_url']}"
        for fact in payload["facts"]
        if EQUITY_ID.fullmatch(str(fact.get("id"))) and fact["id"].endswith(".close")
    ]
    treasury_facts = _text_fact_lines(payload, "treasury.")
    macro_facts = _text_fact_lines(payload, "macro.")
    cross_asset_facts = _text_fact_lines(payload, "cross_asset.")
    lines = [
        f"美股市场日报｜{report_date} 美东报告日",
        f"报告生成时间：{payload['as_of']}；逐项显示原始观测日。",
        "",
        "一、美股市场表现",
        *(market_facts or ["- 暂无经核实指数行情。"]),
        *(_text_claim_lines(grouped["market"]) if grouped["market"] else []),
        "",
        "二、重点个股",
        *equity_facts,
        *_text_claim_lines(grouped["movers"]),
        "",
        "三、美债收益率",
        *(treasury_facts or ["- 暂无经核实的美债收益率水平或日变动。"]),
        "",
        "四、跨资产行情",
        *(cross_asset_facts or ["- 暂无经核实的跨资产行情。"]),
        "",
        "五、市场驱动因素",
        *_text_claim_lines(grouped["drivers"]),
        "",
        "六、经济数据与美联储动态",
        *(macro_facts or ["- 暂无经核实利率与宏观数据。"]),
        *(_text_claim_lines(grouped["macro"]) if grouped["macro"] else []),
        "",
        "七、公司新闻",
        *_text_claim_lines(grouped["company_news"]),
        "",
    ]
    cutoff = payload.get("quality_summary", {}).get("reviewed_source_cutoff")
    if cutoff:
        lines[2:2] = [f"新闻资料截止：{cutoff}。"]
    if payload.get("quality_summary", {}).get("revision") == "historical_backfill":
        lines[2:2] = ["历史补报：本次事后重建，非当日已发布报告。"]
    if grouped["other"]:
        lines.extend(["八、其他已核实内容", *_text_claim_lines(grouped["other"])])
    gaps = _missing_labels(payload)
    if gaps:
        lines.extend(["", f"尚缺：{'、'.join(gaps)}。"])
    lines.extend(["", "风险提示：市场有风险，投资需谨慎。", ""])
    return "\n".join(lines)


def import_report(source: Path, root: Path, manifest_path: Path) -> str:
    from .public_paths import public_snapshot_root

    manifest = _public_manifest(source, manifest_path)
    payload = _public_payload(_read(source), manifest)
    report_date = _date(payload)
    public_root = public_snapshot_root(root)
    data_path = public_root / "data/market_daily_report.json"
    history_path = public_root / "data/market_daily_reports.json"
    report_path = public_root / f"reports/{report_date}-market-daily.md"
    reading_path = public_root / f"reports/{report_date}-market-daily-no-citations.md"
    text_path = public_root / f"reports/{report_date}-market-daily.txt"
    if history_path.is_file():
        previous = json.loads(history_path.read_text(encoding="utf-8"))
        if previous.get(
            "schema_version"
        ) != "market_intel_pages.us_daily_history.v1" or not isinstance(
            previous.get("reports"), list
        ):
            raise ValueError("invalid US daily history index")
        reports = previous["reports"]
    elif data_path.is_file():
        reports = [json.loads(data_path.read_text(encoding="utf-8"))]
    else:
        reports = []
    by_date = {_date(row): row for row in reports}
    older = by_date.get(report_date)
    if older and datetime.fromisoformat(older["generated_at"]) > datetime.fromisoformat(
        payload["generated_at"]
    ):
        raise ValueError("older US daily revision cannot replace newer report")
    by_date[report_date] = payload
    dates = sorted(by_date, reverse=True)[:5]
    if report_date not in dates:
        raise ValueError("US daily report falls outside five-date public window")
    history = {
        "schema_version": "market_intel_pages.us_daily_history.v1",
        "reports": [by_date[day] for day in dates],
    }
    data_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    data_path.write_text(
        json.dumps(history["reports"][0], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.write_text(_markdown(payload), encoding="utf-8")
    reading_path.write_text(_markdown(payload, include_references=False), encoding="utf-8")
    text_path.write_text(_text_report(payload), encoding="utf-8")
    return report_date


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    print(import_report(args.input, args.root, args.manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
