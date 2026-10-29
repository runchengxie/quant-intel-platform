"""Locale catalog and presentation for separate retrospective research evidence."""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from research_contracts.overseas_theme import REJECTION_CODES, EvidenceError, load_evidence

MESSAGES = {
    "en-US": {
        "title": "### Overseas theme research evidence",
        "missing": "- [WARN] Research evidence unavailable ({reason}); overseas moves remain observations.",
        "absent": "not_supplied",
        "status": (
            "Retrospective exploratory study; not a daily forecast. Historical "
            "point-in-time certification: no."
        ),
        "sample": (
            "Study: {study}; sample: {start}–{end}; generated (UTC): "
            "{generated}; revision: {revision}."
        ),
        "row": (
            "{id}: {target}; {outcome}; lag {lag}; n={n}; baseline={baseline}; "
            "augmented={augmented}; MSE gain={gain}, 95% CI [{lo}, {hi}]; "
            "source IDs: {sources}."
        ),
        "meaning": (
            "Positive MSE gain means lower error; negative means higher error. "
            "Intervals spanning zero do not establish improvement."
        ),
        "limit": "Limitation: {text}",
        "source": "Source {id}: [{url}]({url}) (SHA-256 {sha})",
    },
    "zh-CN": {
        "title": "### 海外主题研究证据",
        "missing": "- [WARN] 研究证据不可用（{reason}）；海外行情仅作为观察信息。",
        "absent": "not_supplied",
        "status": "回溯探索性研究，不是当日预测；未经历史时点数据认证。",
        "sample": "研究：{study}；样本：{start}–{end}；生成时间（UTC）：{generated}；源码版本：{revision}。",
        "row": (
            "{id}：{target}；{outcome}；滞后 {lag} "
            "个交易日；n={n}；基线={baseline}；增广={augmented}；MSE 改善={gain}，95% 区间 "
            "[{lo}, {hi}]；来源 ID：{sources}。"
        ),
        "meaning": "MSE 改善为正表示误差下降，为负表示误差上升；区间跨零不能证明存在改善。",
        "limit": "局限：{text}",
        "source": "来源 {id}：[{url}]({url})（SHA-256 {sha}）",
    },
}


def render_evidence(
    evidence: dict | None, locale: str = "en-US", *, rejection: str | None = None
) -> list[str]:
    """Render already validated evidence without ranking or promoting favorable rows."""
    messages = MESSAGES.get(locale, MESSAGES["en-US"])
    lines = [messages["title"]]
    if evidence is None:
        reason = (
            rejection
            if rejection in (*REJECTION_CODES, messages["absent"])
            else ("schema_invalid" if rejection else messages["absent"])
        )
        return [*lines, messages["missing"].format(reason=reason)]
    lines.extend(
        [
            messages["status"],
            messages["sample"].format(
                study=evidence["study_id"],
                start=evidence["sample_start"],
                end=evidence["sample_end"],
                generated=evidence["generated_at_utc"],
                revision=evidence["source_revision"],
            ),
            messages["meaning"],
        ]
    )
    for row in evidence["comparisons"]:
        lines.append(
            messages["row"].format(
                sources=", ".join(row["source_ids"]),
                id=row["evidence_id"],
                target=row["target"],
                outcome=row["outcome"],
                lag=row["lag_sessions"],
                n=row["n"],
                baseline=row["baseline"],
                augmented=row["augmented"],
                gain=f"{row['mse_gain']:.6g}",
                lo=f"{row['mse_gain_ci95'][0]:.6g}",
                hi=f"{row['mse_gain_ci95'][1]:.6g}",
            )
        )
    lines.extend(
        messages["source"].format(id=key, url=value["url"], sha=value["sha256"])
        for key, value in evidence["sources"].items()
    )
    lines.extend(messages["limit"].format(text=value) for value in evidence["limitations"])
    return lines


def evening_evidence(trade_date: str, path: Path | None, sha256: str | None) -> dict:
    """Bound evidence by both actual generation time and the dated report's end."""
    day = datetime.strptime(trade_date, "%Y%m%d").date()
    report_end = datetime.combine(day, time.max, ZoneInfo("Asia/Shanghai"))
    cutoff = min(datetime.now(UTC), report_end.astimezone(UTC))
    evidence, rejection = None, "not_supplied"
    if path is None and sha256 is not None:
        rejection = "unreadable"
    elif path is not None:
        try:
            evidence = load_evidence(path, sha256 or "", cutoff)
            rejection = None
        except EvidenceError as exc:
            rejection = str(exc)
    return {
        "status": "available" if evidence is not None else "unavailable",
        "evidence_cutoff_utc": cutoff.isoformat(),
        "rejection": rejection,
        "evidence": evidence,
    }
