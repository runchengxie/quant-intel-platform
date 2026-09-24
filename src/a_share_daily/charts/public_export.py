"""Fail-closed conversion of private chart manifests to public candidates."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast

from .public_contract import CHART_KEYS, build_candidate

_TITLES = {
    "dashboard": "综合仪表盘",
    "moneyflow": "资金流向图",
    "topic": "热点概念图",
    "sentiment": "情绪指标图",
    "us_overnight": "美股隔夜图",
    "weekly_chart": "周度概览图",
}


def _names(charts: Mapping[str, object], field: str) -> set[str]:
    values = charts.get(field, [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"charts.{field} must be a list of names")
    return set(cast("list[str]", values))


def export_candidate(manifest: object, *, date: str, kind: str) -> dict[str, object]:
    """Whitelist sourced points; private paths, errors and delivery IDs never cross over."""
    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be an object")
    try:
        target = datetime.strptime(date, "%Y%m%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("date must be YYYYMMDD") from exc
    if target.strftime("%Y%m%d") != date or manifest.get("date") != date:
        raise ValueError("manifest date does not match requested date")
    if manifest.get("report_kind") != kind or kind not in ("morning", "evening"):
        raise ValueError("manifest kind does not match requested kind")
    raw_charts = manifest.get("charts")
    if not isinstance(raw_charts, Mapping):
        raise ValueError("manifest charts must be an object")
    charts = cast("Mapping[str, object]", raw_charts)
    points_by_chart = charts.get("public_points", {})
    if not isinstance(points_by_chart, Mapping):
        raise ValueError("charts.public_points must be an object")
    ok = _names(charts, "ok")
    degraded = _names(charts, "degraded")
    skipped = _names(charts, "skipped")
    failed = _names(charts, "failed")

    cards: dict[str, dict[str, object]] = {}
    for key in CHART_KEYS:
        title = "市场温度计" if key == "sentiment" and kind == "evening" else _TITLES[key]
        raw_points = points_by_chart.get(key)
        points = raw_points if isinstance(raw_points, list) else []
        if key in skipped:
            status, reason, points = "skipped", "上游明确跳过该图表", []
        elif key in failed or not points or key not in ok | degraded:
            status, reason, points = "missing", "图表数据或可核实来源缺失", []
        elif key in degraded:
            status, reason = "degraded", "使用替代来源或非目标日观测值"
        else:
            status, reason = "ok", None
        cards[key] = {
            "key": key,
            "title": title,
            "status": status,
            "reason": reason,
            "points": points,
        }
    return build_candidate(
        target.isoformat(), kind, cards, cast("str", manifest.get("generated_at"))
    )
