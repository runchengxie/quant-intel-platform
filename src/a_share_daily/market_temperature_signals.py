"""Contradiction detection and follow-up checks for market temperature.

The calculation module owns normalized metrics and dimension scores.  This
module turns those values into ordered, human-readable tensions and explicit
conditions that can be evaluated on the next observation day.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Mapping, Sequence
from typing import Any


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _rounded(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _dimension_score(dimensions: Mapping[str, Mapping[str, Any]], name: str) -> float | None:
    return _number(dimensions[name].get("score"))


def _tension(
    tension_id: str,
    summary: str,
    evidence: Mapping[str, float | None],
    severity: str = "medium",
) -> dict[str, Any]:
    return {
        "id": tension_id,
        "severity": severity,
        "summary": summary,
        "evidence": {key: _rounded(value) for key, value in evidence.items()},
    }


def _dimension_tensions(
    dimensions: Mapping[str, Mapping[str, Any]], metrics: Mapping[str, float | None]
) -> list[dict[str, Any]]:
    breadth = _dimension_score(dimensions, "breadth")
    profit = _dimension_score(dimensions, "profit_effect")
    loss = _dimension_score(dimensions, "loss_risk")
    rotation = _dimension_score(dimensions, "rotation_quality")
    tensions: list[dict[str, Any]] = []
    if profit is not None and breadth is not None and profit >= 55 and breadth <= 42:
        tensions.append(
            _tension(
                "hotspots_vs_breadth",
                "局部赚钱效应较强，但全市场参与度偏弱",
                {"profit_effect_score": profit / 100, "breadth_score": breadth / 100},
                "high",
            )
        )
    if loss is not None and profit is not None and loss >= 55 and profit >= 55:
        tensions.append(
            _tension(
                "opportunity_and_loss_coexist",
                "赚钱效应与亏钱风险同时偏高，追涨容错率有限",
                {"profit_effect_score": profit / 100, "loss_risk_score": loss / 100},
                "high",
            )
        )
    if rotation is not None and breadth is not None and rotation >= 60 and breadth <= 42:
        tensions.append(
            _tension(
                "rotation_vs_stock_breadth",
                "行业层面多数上涨，但个股广度没有同步确认",
                {
                    "industry_positive_ratio": metrics["industry_positive_ratio"],
                    "breadth_up_ratio": metrics["breadth_up_ratio"],
                },
            )
        )
    return tensions


def _index_breadth_tensions(
    metrics: Mapping[str, float | None],
) -> list[dict[str, Any]]:
    index_positive = metrics["index_positive_ratio"]
    breadth_ratio = metrics["breadth_up_ratio"]
    tensions: list[dict[str, Any]] = []
    if (
        index_positive is not None
        and breadth_ratio is not None
        and index_positive >= 0.60
        and breadth_ratio <= 0.40
    ):
        tensions.append(
            _tension(
                "indices_vs_stock_breadth",
                "主要指数表现与个股涨跌广度背离",
                {"index_positive_ratio": index_positive, "breadth_up_ratio": breadth_ratio},
                "high",
            )
        )
    if (
        index_positive is not None
        and breadth_ratio is not None
        and breadth_ratio >= 0.55
        and index_positive <= 0.40
    ):
        tensions.append(
            _tension(
                "stock_breadth_vs_indices",
                "多数个股上涨，但主要指数没有同步确认",
                {"breadth_up_ratio": breadth_ratio, "index_positive_ratio": index_positive},
                "high",
            )
        )
    return tensions


def _market_quality_tensions(
    dimensions: Mapping[str, Mapping[str, Any]], metrics: Mapping[str, float | None]
) -> list[dict[str, Any]]:
    breadth = _dimension_score(dimensions, "breadth")
    liquidity = _dimension_score(dimensions, "liquidity")
    breadth_ratio = metrics["breadth_up_ratio"]
    tensions: list[dict[str, Any]] = []
    median_return = metrics["median_return"]
    weighted_return = metrics["turnover_weighted_return"]
    if (
        median_return is not None
        and weighted_return is not None
        and median_return - weighted_return >= 0.01
    ):
        tensions.append(
            _tension(
                "stock_median_vs_turnover_weighted",
                "个股中位数修复，但高成交标的明显承压",
                {"median_return": median_return, "turnover_weighted_return": weighted_return},
                "high",
            )
        )
    vwap_ratio = metrics["vwap_above_ratio"]
    if (
        breadth_ratio is not None
        and vwap_ratio is not None
        and breadth_ratio >= 0.55
        and vwap_ratio < 0.50
    ):
        tensions.append(
            _tension(
                "close_breadth_vs_vwap",
                "收盘上涨家数占优，但站上日内均价的个股不足一半",
                {"breadth_up_ratio": breadth_ratio, "vwap_above_ratio": vwap_ratio},
            )
        )
    flow_positive = metrics["flow_positive_stock_ratio"]
    if (
        flow_positive is not None
        and breadth_ratio is not None
        and flow_positive - breadth_ratio >= 0.15
    ):
        tensions.append(
            _tension(
                "flow_vs_price_breadth",
                "资金净流入覆盖面没有转化为同等价格广度",
                {"flow_positive_stock_ratio": flow_positive, "breadth_up_ratio": breadth_ratio},
            )
        )
    if liquidity is not None and breadth is not None and liquidity >= 65 and breadth <= 40:
        tensions.append(
            _tension(
                "liquidity_without_participation",
                "流动性活跃，但上涨参与度不足",
                {"liquidity_score": liquidity / 100, "breadth_score": breadth / 100},
            )
        )
    return tensions


def build_core_tensions(
    dimensions: Mapping[str, Mapping[str, Any]], metrics: Mapping[str, float | None]
) -> list[dict[str, Any]]:
    """Return detected tensions in stable report-priority order."""
    tensions = _dimension_tensions(dimensions, metrics)
    tensions.extend(_index_breadth_tensions(metrics))
    tensions.extend(_market_quality_tensions(dimensions, metrics))
    return tensions


def _breadth_repair_condition(
    trade_date: str, tension_ids: set[str], metrics: Mapping[str, float | None]
) -> dict[str, Any] | None:
    breadth = metrics["breadth_up_ratio"]
    relevant_tensions = {
        "hotspots_vs_breadth",
        "rotation_vs_stock_breadth",
        "indices_vs_stock_breadth",
        "flow_vs_price_breadth",
        "liquidity_without_participation",
    }
    if breadth is None or not tension_ids & relevant_tensions:
        return None
    return {
        "id": "breadth_repair",
        "origin_trade_date": trade_date,
        "metric": "breadth_up_ratio",
        "operator": ">",
        "target": round(breadth, 4),
        "description": "下一观察日上涨家数占比高于当前值，才算广度开始修复",
    }


def _index_repair_condition(
    trade_date: str, tension_ids: set[str], metrics: Mapping[str, float | None]
) -> dict[str, Any] | None:
    index_positive = metrics["index_positive_ratio"]
    if index_positive is None or "stock_breadth_vs_indices" not in tension_ids:
        return None
    return {
        "id": "index_participation_repair",
        "origin_trade_date": trade_date,
        "metric": "index_positive_ratio",
        "operator": ">",
        "target": round(index_positive, 4),
        "description": "下一观察日主要指数上涨占比高于当前值，才算指数确认开始修复",
    }


def _weighted_return_condition(
    trade_date: str, tension_ids: set[str], metrics: Mapping[str, float | None]
) -> dict[str, Any] | None:
    weighted_return = metrics["turnover_weighted_return"]
    if weighted_return is None or "stock_median_vs_turnover_weighted" not in tension_ids:
        return None
    return {
        "id": "turnover_weighted_repair",
        "origin_trade_date": trade_date,
        "metric": "turnover_weighted_return",
        "operator": ">=",
        "target": 0.0,
        "description": "下一观察日成交额加权涨跌转为非负，才算高成交方向止跌",
    }


def _vwap_condition(
    trade_date: str, tension_ids: set[str], metrics: Mapping[str, float | None]
) -> dict[str, Any] | None:
    vwap_ratio = metrics["vwap_above_ratio"]
    if vwap_ratio is None or "close_breadth_vs_vwap" not in tension_ids:
        return None
    return {
        "id": "vwap_confirmation",
        "origin_trade_date": trade_date,
        "metric": "vwap_above_ratio",
        "operator": ">=",
        "target": 0.50,
        "description": "下一观察日站上日内均价的个股达到一半，才算上涨质量改善",
    }


def _loss_tail_condition(
    trade_date: str, tension_ids: set[str], metrics: Mapping[str, float | None]
) -> dict[str, Any] | None:
    down5 = metrics["down5_ratio"]
    up5 = metrics["up5_ratio"]
    loss_score_trigger = (
        down5 is not None and up5 is not None and down5 > up5
    ) or "opportunity_and_loss_coexist" in tension_ids
    if down5 is None or not loss_score_trigger:
        return None
    return {
        "id": "loss_tail_cooling",
        "origin_trade_date": trade_date,
        "metric": "down5_ratio",
        "operator": "<",
        "target": round(down5, 4),
        "description": "下一观察日跌幅超过 5% 的占比下降，才算尾部亏钱效应缓和",
    }


def build_validation_conditions(
    trade_date: str,
    tensions: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, float | None],
) -> list[dict[str, Any]]:
    """Return next-observation checks in stable report-priority order."""
    tension_ids = {str(item.get("id")) for item in tensions}
    candidates = (
        _breadth_repair_condition(trade_date, tension_ids, metrics),
        _index_repair_condition(trade_date, tension_ids, metrics),
        _weighted_return_condition(trade_date, tension_ids, metrics),
        _loss_tail_condition(trade_date, tension_ids, metrics),
        _vwap_condition(trade_date, tension_ids, metrics),
    )
    return [condition for condition in candidates if condition is not None]


_OPERATORS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}


def evaluate_conditions(
    previous_conditions: Sequence[Mapping[str, Any]] | None,
    current_metrics: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Evaluate prior conditions against current normalized metrics."""
    if not previous_conditions:
        return []
    current_metrics = current_metrics or {}
    nested = current_metrics.get("metrics") if isinstance(current_metrics, Mapping) else None
    if isinstance(nested, Mapping):
        current_metrics = nested

    evaluations: list[dict[str, Any]] = []
    for condition in previous_conditions:
        result = dict(condition)
        metric_name = str(condition.get("metric", ""))
        operation = str(condition.get("operator", ""))
        observed = _number(current_metrics.get(metric_name))
        target = _number(condition.get("target"))
        compare = _OPERATORS.get(operation)
        result["observed"] = _rounded(observed)
        if observed is None:
            result.update(status="not_evaluable", reason="current_metric_missing")
        elif target is None or compare is None:
            result.update(status="not_evaluable", reason="condition_invalid")
        else:
            result["status"] = "confirmed" if compare(observed, target) else "invalidated"
            result["distance_to_target"] = _rounded(observed - target)
        evaluations.append(result)
    return evaluations


__all__ = [
    "build_core_tensions",
    "build_validation_conditions",
    "evaluate_conditions",
]
