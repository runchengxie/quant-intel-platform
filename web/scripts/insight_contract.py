"""Evidence and observable-condition contracts for market commentary.

Model prose is an interpretation, not a verified fact. References and numerical
claims are checked here; outcomes are calculated from subsequent source reports.
"""

from __future__ import annotations

import hashlib
import json
import math
import operator
import re
from datetime import datetime

try:
    from .generate_daily_summary import report_generated_at
except ImportError:
    from generate_daily_summary import report_generated_at

METRICS = {
    "advancing_pct": ("上涨率", r"上涨率[:：]?\s*([\d.]+)%", "%"),
    "volume_ratio": ("成交额 / 历史中位数", r"成交额/历史中位\s*([\d.]+)x", "倍"),
    "tail_loss_pct": ("跌幅超过 5% 占比", r"跌幅超(?:过)?5%占比[:：]?\s*([\d.]+)%", "%"),
    "above_vwap_pct": ("站上 VWAP 占比", r"站上\s*VWAP\s*(?:占比|比例)[:：]?\s*([\d.]+)%", "%"),
}
OPERATORS = {">": operator.gt, "<": operator.lt, ">=": operator.ge, "<=": operator.le}


def source_hash(reports: list[dict]) -> str:
    raw = json.dumps(
        sorted(reports, key=lambda row: row["id"]), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def evidence_for(reports: list[dict]) -> list[dict]:
    evidence = []
    for row in reports:
        for si, section in enumerate(row.get("sections", [])):
            for pi, paragraph in enumerate(section.get("paragraphs", [])):
                if not isinstance(paragraph, str) or not paragraph.strip():
                    continue
                evidence.append(
                    {
                        "id": f"{row['id']}:s{si}:p{pi}",
                        "report_id": row["id"],
                        "section": section.get("title", ""),
                        "text": paragraph,
                    }
                )
    return evidence


def extract_metrics(report: dict) -> dict:
    result = {}
    evidence = evidence_for([report])
    for key, (label, pattern, unit) in METRICS.items():
        matches = [(float(m[1]), item["id"]) for item in evidence for m in re.finditer(pattern, item["text"])]
        # Conflicting source values must not silently become a successful check.
        if matches and len({v for v, _ in matches}) == 1:
            result[key] = {
                "value": matches[0][0],
                "label": label,
                "unit": unit,
                "evidence_ids": [ref for _, ref in matches],
            }
    return result


def build_context(reports: list[dict], morning: dict, evening: dict) -> dict:
    cutoff = report_generated_at(morning)
    evening_time = report_generated_at(evening)
    if (
        cutoff is None
        or evening_time is None
        or evening_time >= cutoff
        or morning.get("kind") != "morning"
        or evening.get("kind") != "evening"
        or evening["date"] > morning["date"]
    ):
        raise ValueError("invalid source pair or timestamps")
    eligible = [
        row
        for row in reports
        if (generated := report_generated_at(row)) is not None
        and generated <= cutoff
        and row["date"] <= morning["date"]
    ]
    dates = sorted({row["date"] for row in eligible}, reverse=True)[:5]
    selected = sorted([row for row in eligible if row["date"] in dates], key=lambda row: row["id"])
    evidence = evidence_for(selected)
    warnings = list(
        dict.fromkeys(
            e["text"]
            for e in evidence
            if e["report_id"] in (morning["id"], evening["id"])
            and re.search(r"缺失|暂缺|不可用|未取得|降级|不匹配|未回测", e["text"])
        )
    )
    return {
        "as_of": cutoff.isoformat(),
        "date": morning["date"],
        "morning_report_id": morning["id"],
        "evening_report_id": evening["id"],
        "source_report_ids": [row["id"] for row in selected],
        "source_hashes": {row["id"]: source_hash([row]) for row in selected},
        "source_hash": source_hash(selected),
        "evidence": evidence,
        "metrics": extract_metrics(evening),
        "quality_warnings": warnings[:12],
    }


def _text(value, maximum=220):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("invalid commentary text")


def _references(item, evidence):
    refs = item.get("evidence_ids")
    if (
        not isinstance(refs, list)
        or not 1 <= len(refs) <= 6
        or any(not isinstance(ref, str) or ref not in evidence for ref in refs)
    ):
        raise ValueError("unknown or missing evidence")
    return " ".join(evidence[ref]["text"] for ref in refs)


def _validate_watchpoint(point: dict, context: dict, evidence: dict) -> None:
    if not isinstance(point, dict) or set(point) != {
        "question",
        "metric",
        "operator",
        "threshold",
        "evidence_ids",
    }:
        raise ValueError("invalid watchpoint")
    _text(point["question"], 100)
    _references(point, evidence)
    baseline = context["metrics"].get(point["metric"])
    threshold = point["threshold"]
    if (
        not baseline
        or point["operator"] not in OPERATORS
        or isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
        or threshold != baseline["value"]
        or not set(point["evidence_ids"]) & set(baseline["evidence_ids"])
    ):
        raise ValueError("watch condition must use a cited baseline metric")


def validate_analysis(payload: dict, context: dict) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"overview", "changes", "tensions", "watchpoints"}:
        raise ValueError("invalid analysis schema")
    evidence = {item["id"]: item for item in context["evidence"]}
    claims = [payload["overview"]]
    for key in ("changes", "tensions"):
        if not isinstance(payload[key], list) or not 1 <= len(payload[key]) <= 3:
            raise ValueError("invalid claim count")
        claims.extend(payload[key])
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"text", "evidence_ids"}:
            raise ValueError("invalid claim")
        _text(claim["text"])
        quoted = _references(claim, evidence)
        # Exact source tokens: no invented prices, probabilities or precise levels.
        numbers = set(re.findall(r"[+-]?\d+(?:\.\d+)?%?", quoted))
        if any(n not in numbers for n in re.findall(r"[+-]?\d+(?:\.\d+)?%?", claim["text"])):
            raise ValueError("number not supported by cited evidence")
    points = payload["watchpoints"]
    if not isinstance(points, list) or len(points) > 3:
        raise ValueError("invalid watchpoint count")
    for point in points:
        _validate_watchpoint(point, context, evidence)
    if sum(len(c["text"]) for c in claims) > 700:
        raise ValueError("commentary too long")
    return payload


def _next_evening(note: dict, reports: list[dict]) -> dict | None:
    cutoff = datetime.fromisoformat(note["as_of"])
    candidates = [
        row
        for row in reports
        if row.get("kind") == "evening"
        and row["date"] > note["date"]
        and (generated := report_generated_at(row)) is not None
        and generated > cutoff
    ]
    return min(candidates, key=lambda row: (row["date"], report_generated_at(row))) if candidates else None


def _watchpoint_outcome(note_id: str, index: int, point: dict, later: dict | None) -> dict:
    result = {
        "insight_id": note_id,
        "watchpoint_index": index,
        "status": "pending",
        "report_id": None,
        "observed_date": None,
        "observed_value": None,
        "evidence_ids": [],
        "evidence": [],
        "source_hash": None,
    }
    if later is None:
        return result
    result.update(
        status="unverifiable",
        report_id=later["id"],
        observed_date=later["date"],
        source_hash=source_hash([later]),
    )
    metric = extract_metrics(later).get(point["metric"])
    if metric is None:
        return result
    satisfied = OPERATORS[point["operator"]](metric["value"], point["threshold"])
    result.update(
        status="met" if satisfied else "not_met",
        observed_value=metric["value"],
        evidence_ids=metric["evidence_ids"],
        evidence=[item for item in evidence_for([later]) if item["id"] in metric["evidence_ids"]],
    )
    return result


def evaluate_watchpoints(insights: list[dict], reports: list[dict]) -> list[dict]:
    outcomes = []
    for note in insights:
        later = _next_evening(note, reports)
        outcomes.extend(
            _watchpoint_outcome(note["id"], index, point, later)
            for index, point in enumerate(note["analysis"]["watchpoints"])
        )
    return outcomes
