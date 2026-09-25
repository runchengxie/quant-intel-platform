"""Fail-closed conversion of private chart manifests to public candidates."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from datetime import date as date_type
from datetime import datetime
from typing import cast

from .public_contract import CHART_KEYS, build_candidate
from .us_overnight import SYMBOLS

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


def _moneyflow_day(points: list[object]) -> date_type | None:
    dates = {str(item.get("observation_date")) for item in points if isinstance(item, Mapping)}
    if len(dates) == 1:
        with contextlib.suppress(TypeError, ValueError):
            return date_type.fromisoformat(next(iter(dates)))
    return None


def _points(source: Mapping[str, object], key: str) -> list[object]:
    value = source.get(key)
    return cast("list[object]", value) if isinstance(value, list) else []


def _dashboard_margin_stale(points: list[object], target: date_type) -> bool:
    dates = {
        str(item.get("observation_date"))
        for item in points
        if isinstance(item, Mapping) and str(item.get("label", "")).startswith("成交额 ")
    }
    previous = max((day for day in dates if day < target.isoformat()), default=None)
    if previous is None:
        return False
    margin_dates = [
        str(item.get("observation_date"))
        for item in points
        if isinstance(item, Mapping) and str(item.get("label", "")).startswith("融资余额 ")
    ]
    return not margin_dates or max(margin_dates) < previous


def _chart_card(
    key: str,
    *,
    kind: str,
    target: date_type,
    points: list[object],
    ok: set[str],
    degraded: set[str],
    failed: set[str],
    skipped: set[str],
    errors: Mapping[str, object],
) -> dict[str, object]:
    title = "市场温度计" if key == "sentiment" and kind == "evening" else _TITLES[key]
    moneyflow_day = _moneyflow_day(points) if key == "moneyflow" else None
    known_fallback = (
        key == "moneyflow"
        and moneyflow_day is not None
        and moneyflow_day < target
        and errors.get(key)
        == f"moneyflow_ths {target.strftime('%Y%m%d')} 暂缺，使用最新可用 {moneyflow_day.strftime('%Y%m%d')}"
    )
    if key in skipped:
        status, reason, points = "skipped", "上游明确跳过该图表", []
    elif kind == "evening" and key == "sentiment":
        status, reason, points = "missing", "晚报市场温度计尚无同口径已核实点集", []
    elif key in failed or not points or key not in ok | degraded:
        status, reason, points = "missing", "图表数据或可核实来源缺失", []
    elif key in errors and not known_fallback:
        status, reason, points = "missing", "上游图表生成报错，不能凭保留点集发布", []
    elif key == "moneyflow" and moneyflow_day is not None and moneyflow_day > target:
        status, reason, points = "missing", "观测日晚于报告日", []
    elif key == "us_overnight" and len(points) < len(SYMBOLS):
        status, reason = "degraded", "部分美股行情缺少可核实收盘日或来源"
    elif key == "dashboard" and _dashboard_margin_stale(points, target):
        status, reason = "degraded", "融资余额最新观测日早于上一交易日，保留原始观测日"
    elif key in degraded or (
        key == "moneyflow" and moneyflow_day is not None and moneyflow_day < target
    ):
        status, reason = "degraded", "使用替代来源或非目标日观测值"
    else:
        status, reason = "ok", None
    return {"key": key, "title": title, "status": status, "reason": reason, "points": points}


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
    points_by_chart = cast("Mapping[str, object]", points_by_chart)
    ok = _names(charts, "ok")
    degraded = _names(charts, "degraded")
    skipped = _names(charts, "skipped")
    failed = _names(charts, "failed")
    raw_errors = charts.get("errors", {})
    if not isinstance(raw_errors, Mapping):
        raise ValueError("charts.errors must be an object")
    raw_errors = cast("Mapping[str, object]", raw_errors)

    cards = {
        key: _chart_card(
            key,
            kind=kind,
            target=target,
            points=_points(points_by_chart, key),
            ok=ok,
            degraded=degraded,
            failed=failed,
            skipped=skipped,
            errors=raw_errors,
        )
        for key in CHART_KEYS
    }
    return build_candidate(
        target.isoformat(), kind, cards, cast("str", manifest.get("generated_at"))
    )
