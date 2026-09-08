"""Build the auditable composite topic summary for daily reports."""

from __future__ import annotations

from typing import Any

import pandas as pd


def build_fallback_topic_summary(
    trade_date: str,
    *,
    concept: pd.DataFrame,
    members: pd.DataFrame,
    limits: pd.DataFrame,
    moneyflow: pd.DataFrame,
    daily: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Backward-compatible name for the composite topic builder."""
    return build_composite_topic_summary(
        trade_date,
        concept=concept,
        members=members,
        limits=limits,
        moneyflow=moneyflow,
        daily=daily,
    )


def build_composite_topic_summary(
    trade_date: str,
    *,
    concept: pd.DataFrame,
    members: pd.DataFrame,
    limits: pd.DataFrame,
    moneyflow: pd.DataFrame,
    daily: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Rank concepts with identity, confirmation, and optional breadth layers."""
    if concept.empty or members.empty:
        raise ValueError("composite hotspot core identity data is empty")
    member_counts = members.groupby("theme_code")["ts_code"].nunique()
    limit_counts = _counts_by_theme(members, limits, "limit_type", "涨停")
    flow = _moneyflow_by_theme(members, moneyflow)
    breadth = _breadth_by_theme(members, daily)
    rows: list[dict[str, Any]] = []
    for _, row in concept.iterrows():
        code = str(row.get("theme_code", ""))
        name = str(row.get("name", "")).strip()
        if not code or not name:
            continue
        pct = _number(row.get("pct_change"))
        main = _number(row.get("main_change"))
        hot = _number(row.get("hot"))
        limit_up = int(limit_counts.get(code, 0))
        net_flow = float(flow.get(code, 0.0))
        count = int(member_counts.get(code, 0))
        breadth_score, positive_ratio = breadth.get(code, (0.0, 0.0))
        identity_score = max(pct, 0.0) + max(main, 0.0) / 1e8 + max(hot, 0.0) / 10000
        confirmation_score = limit_up * 0.5 + max(net_flow, 0.0) / 1e5
        score = identity_score + confirmation_score + breadth_score
        if score <= 0:
            continue
        rows.append(
            {
                "topic": name,
                "count": max(count, 1),
                "weight": round(score, 6),
                "limit_up_count": limit_up,
                "moneyflow_net_amount": round(net_flow, 6),
                "positive_ratio": round(positive_ratio, 6),
            }
        )
    rows.sort(key=lambda item: (-item["weight"], item["topic"]))
    rows = rows[:20]
    total = sum(item["weight"] for item in rows)
    if total <= 0:
        raise ValueError("fallback concept data has no positive topic score")
    for rank, item in enumerate(rows, 1):
        item["rank"] = rank
    source_status = {
        "dc_concept": "passed",
        "dc_concept_cons": "passed",
        "limit_list_ths": "passed" if not limits.empty else "missing_optional",
        "moneyflow_ths": "passed" if not moneyflow.empty else "missing_optional",
        "daily": "passed" if daily is not None and not daily.empty else "missing_optional",
    }
    degraded = any(value == "missing_optional" for value in source_status.values())
    return {
        "schema_version": "daily_watch20.topic_summary.v1",
        "artifact_type": "daily_watch20_topic_summary",
        "source_date": trade_date,
        "signal_date": trade_date,
        "source": "hotspot_composite_v1",
        "degraded": degraded,
        "aggregation": "identity_plus_confirmation_plus_optional_breadth_v1",
        "providers": {
            "concept_identity": "dc_concept",
            "concept_members": "dc_concept_cons",
            "market_confirmation": ["limit_list_ths", "moneyflow_ths"],
            "breadth": "daily" if daily is not None and not daily.empty else None,
        },
        "source_status": source_status,
        "topics": rows,
        "quality": {"status": "passed", "selected_count": sum(i["count"] for i in rows), "topic_count": len(rows)},
    }


def _number(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _counts_by_theme(members: pd.DataFrame, evidence: pd.DataFrame, column: str, value: str) -> dict[str, int]:
    if evidence.empty or column not in evidence or "ts_code" not in evidence:
        return {}
    selected = evidence[evidence[column].astype(str).str.contains(value, na=False)]
    return selected.merge(members[["theme_code", "ts_code"]].drop_duplicates(), on="ts_code").groupby("theme_code").size().to_dict()


def _moneyflow_by_theme(members: pd.DataFrame, moneyflow: pd.DataFrame) -> dict[str, float]:
    if moneyflow.empty or "net_amount" not in moneyflow or "ts_code" not in moneyflow:
        return {}
    joined = moneyflow[["ts_code", "net_amount"]].merge(members[["theme_code", "ts_code"]], on="ts_code")
    joined["net_amount"] = pd.to_numeric(joined["net_amount"], errors="coerce").fillna(0.0)
    return joined.groupby("theme_code")["net_amount"].sum().to_dict()


def _breadth_by_theme(
    members: pd.DataFrame, daily: pd.DataFrame | None
) -> dict[str, tuple[float, float]]:
    if daily is None or daily.empty or "ts_code" not in daily:
        return {}
    change_column = "pct_chg" if "pct_chg" in daily else "change_pct" if "change_pct" in daily else ""
    if not change_column:
        return {}
    prices = daily[["ts_code", change_column]].copy()
    prices["ts_code"] = prices["ts_code"].astype(str).str.strip().str.upper()
    prices[change_column] = pd.to_numeric(prices[change_column], errors="coerce")
    joined = members[["theme_code", "ts_code"]].drop_duplicates().merge(prices, on="ts_code")
    if joined.empty:
        return {}
    grouped = joined.groupby("theme_code")[change_column]
    return {
        str(theme): (max(float(values.mean()), 0.0) * 0.1, float(values.gt(0).mean()))
        for theme, values in grouped
    }
