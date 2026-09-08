"""Dimension assembly and the public market-temperature builder.

This submodule wires the low-level metric helpers (in
:mod:`a_share_daily.temperature_metrics`) into six named dimensions, a composite
heat score, a fragility score, a confidence estimate, and finally the public
:func:`build_market_temperature` entry point.

Cross-submodule calls use the ``_metrics`` alias (``from . import
temperature_metrics as _metrics``) rather than local re-bindings, so that any
future test which monkeypatches a metric function keeps the same observable
effect across the dimensions layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from . import temperature_metrics as _metrics
from .market_temperature_signals import (
    build_core_tensions,
    build_validation_conditions,
    evaluate_conditions,
)

CALIBRATION = "provisional_observation_scale"

_DIMENSION_WEIGHTS = {
    "liquidity": 0.15,
    "breadth": 0.25,
    "profit_effect": 0.20,
    "loss_risk": 0.15,
    "trend_confirmation": 0.15,
    "rotation_quality": 0.10,
}


def _dimension(
    label: str,
    score_parts: Sequence[float | None],
    metrics: Mapping[str, float | None],
    *,
    polarity: str = "higher_is_supportive",
    required_present: bool = True,
) -> dict[str, Any]:
    available_parts = [part for part in score_parts if part is not None]
    score = _metrics._mean(available_parts) if required_present else None
    return {
        "label": label,
        "score": round(score, 1) if score is not None else None,
        "polarity": polarity,
        "coverage": round(len(available_parts) / len(score_parts), 2) if score_parts else 0.0,
        "metrics": {key: _metrics._rounded(value) for key, value in metrics.items()},
    }


def _participation_dimensions(
    metrics: Mapping[str, float | None],
) -> dict[str, dict[str, Any]]:
    return {
        "liquidity": _dimension(
            "流动性",
            [
                _metrics._score_between(metrics["turnover_vs_median"], 0.75, 1.25),
                None
                if metrics["turnover_percentile"] is None
                else round(metrics["turnover_percentile"] * 100, 1),
            ],
            {
                "turnover_vs_median": metrics["turnover_vs_median"],
                "turnover_percentile": metrics["turnover_percentile"],
            },
            required_present=metrics["turnover_vs_median"] is not None,
        ),
        "breadth": _dimension(
            "广度",
            [
                _metrics._score_between(metrics["breadth_up_ratio"], 0.25, 0.75),
                _metrics._score_between(metrics["median_return"], -0.02, 0.02),
                _metrics._score_between(metrics["vwap_above_ratio"], 0.30, 0.70),
            ],
            {
                "breadth_up_ratio": metrics["breadth_up_ratio"],
                "median_return": metrics["median_return"],
                "vwap_above_ratio": metrics["vwap_above_ratio"],
            },
            required_present=metrics["breadth_up_ratio"] is not None,
        ),
        "profit_effect": _dimension(
            "赚钱效应",
            [
                _metrics._score_between(metrics["limit_up_ratio"], 0.002, 0.018),
                _metrics._score_between(metrics["up5_ratio"], 0.01, 0.06),
                _metrics._score_between(metrics["seal_rate"], 0.40, 0.90),
            ],
            {
                "limit_up_ratio": metrics["limit_up_ratio"],
                "up5_ratio": metrics["up5_ratio"],
                "seal_rate": metrics["seal_rate"],
            },
            required_present=(
                metrics["limit_up_ratio"] is not None or metrics["up5_ratio"] is not None
            ),
        ),
    }


def _risk_and_trend_dimensions(
    metrics: Mapping[str, float | None],
) -> dict[str, dict[str, Any]]:
    dimensions: dict[str, dict[str, Any]] = {
        "loss_risk": _dimension(
            "亏钱风险",
            [
                _metrics._score_between(metrics["limit_down_ratio"], 0.001, 0.012),
                _metrics._score_between(metrics["down5_ratio"], 0.01, 0.06),
                _metrics._score_between(metrics["failed_board_ratio"], 0.10, 0.60),
            ],
            {
                "limit_down_ratio": metrics["limit_down_ratio"],
                "down5_ratio": metrics["down5_ratio"],
                "failed_board_ratio": metrics["failed_board_ratio"],
            },
            polarity="higher_is_risk",
            required_present=(
                metrics["limit_down_ratio"] is not None or metrics["down5_ratio"] is not None
            ),
        ),
        "trend_confirmation": _dimension(
            "趋势确认",
            [
                None
                if metrics["index_positive_ratio"] is None
                else round(metrics["index_positive_ratio"] * 100, 1),
                _metrics._score_between(metrics["index_median_return"], -0.015, 0.015),
                _metrics._score_between(metrics["index_close_position"], 0.20, 0.80),
            ],
            {
                "index_positive_ratio": metrics["index_positive_ratio"],
                "index_median_return": metrics["index_median_return"],
                "index_close_position": metrics["index_close_position"],
            },
            required_present=(
                metrics["index_positive_ratio"] is not None
                or metrics["index_median_return"] is not None
            ),
        ),
    }
    # trend_confirmation scores None only when the index_daily snapshot is
    # missing/stale. Surface that explicitly in the report so the bare "N/A"
    # does not read like a real neutral observation. The renderer's
    # _dimension_status / _dimension_evidence pick up these keys.
    trend = dimensions["trend_confirmation"]
    if trend["score"] is None:
        trend["status"] = "数据缺失"
        trend["note"] = "指数行情未刷新，趋势确认不可用"
    return dimensions


def _rotation_dimensions(
    metrics: Mapping[str, float | None],
) -> dict[str, dict[str, Any]]:
    return {
        "rotation_quality": _dimension(
            "轮动质量",
            [
                None
                if metrics["industry_positive_ratio"] is None
                else round(metrics["industry_positive_ratio"] * 100, 1),
                _metrics._score_between(metrics["industry_median_return"], -0.015, 0.015),
                None
                if metrics["leadership_concentration"] is None
                else _metrics._score_between(1 - metrics["leadership_concentration"], 0.25, 0.75),
            ],
            {
                "industry_positive_ratio": metrics["industry_positive_ratio"],
                "industry_median_return": metrics["industry_median_return"],
                "leadership_concentration": metrics["leadership_concentration"],
            },
            required_present=(
                metrics["industry_positive_ratio"] is not None
                or metrics["industry_median_return"] is not None
            ),
        ),
    }


def _build_dimensions(metrics: Mapping[str, float | None]) -> dict[str, dict[str, Any]]:
    dimensions = _participation_dimensions(metrics)
    dimensions.update(_risk_and_trend_dimensions(metrics))
    dimensions.update(_rotation_dimensions(metrics))
    return dimensions


def _composite_heat(dimensions: Mapping[str, Mapping[str, Any]]) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for name, weight in _DIMENSION_WEIGHTS.items():
        score = _metrics._number(dimensions[name].get("score"))
        if score is None:
            continue
        contribution = 100 - score if name == "loss_risk" else score
        numerator += contribution * weight
        denominator += weight
    return round(numerator / denominator, 1) if denominator else None


def _fragility_score(
    dimensions: Mapping[str, Mapping[str, Any]], metrics: Mapping[str, float | None]
) -> float | None:
    weighted_factors: list[tuple[float | None, float]] = []
    loss = _metrics._number(dimensions["loss_risk"].get("score"))
    breadth = _metrics._number(dimensions["breadth"].get("score"))
    rotation = _metrics._number(dimensions["rotation_quality"].get("score"))
    weighted_factors.extend(
        (
            (loss, 0.45),
            (None if breadth is None else 100 - breadth, 0.10),
            (None if rotation is None else 100 - rotation, 0.05),
        )
    )

    index_positive = metrics["index_positive_ratio"]
    breadth_ratio = metrics["breadth_up_ratio"]
    divergence = None
    if index_positive is not None and breadth_ratio is not None:
        divergence = 100 * _metrics._clamp(abs(index_positive - breadth_ratio))
    weighted_factors.append((divergence, 0.30))

    flow_positive = metrics["flow_positive_stock_ratio"]
    flow_divergence = None
    if flow_positive is not None and breadth_ratio is not None:
        flow_divergence = 100 * _metrics._clamp(abs(flow_positive - breadth_ratio))
    weighted_factors.append((flow_divergence, 0.10))

    present = [(value, weight) for value, weight in weighted_factors if value is not None]
    if not present:
        return None
    denominator = sum(weight for _value, weight in present)
    return round(sum(value * weight for value, weight in present) / denominator, 1)


def _confidence(
    dimensions: Mapping[str, Mapping[str, Any]],
    *,
    overview: Mapping[str, Any],
    indices: Any,
    limits: Mapping[str, Any],
    moneyflow: Mapping[str, Any],
    industries: Any,
    turnover_history: Any,
) -> float:
    available = [item for item in dimensions.values() if item.get("score") is not None]
    dimension_availability = len(available) / len(_DIMENSION_WEIGHTS)
    metric_coverage = (
        _metrics._mean([_metrics._number(item.get("coverage")) for item in dimensions.values()])
        or 0.0
    )
    input_availability = (
        sum(
            (
                bool(overview),
                bool(_metrics._records(indices)),
                bool(limits),
                bool(moneyflow),
                bool(_metrics._records(industries)),
                len(_metrics._history_values(turnover_history)) >= 3,
            )
        )
        / 6
    )
    return round(
        0.60 * dimension_availability + 0.25 * metric_coverage + 0.15 * input_availability, 2
    )


def _data_warnings(
    dimensions: Mapping[str, Mapping[str, Any]],
    *,
    limits: Mapping[str, Any],
    turnover_history: Any,
) -> list[str]:
    warnings: list[str] = []
    limit_down = limits.get("limit_down")
    method = limit_down.get("method") if isinstance(limit_down, Mapping) else None
    if method and method != "exchange_limit_price":
        warnings.append("涨跌停未使用交易所当日限价，当前为近似或涨停池口径")

    partial = [
        str(item.get("label"))
        for item in dimensions.values()
        if item.get("score") is not None and (_metrics._number(item.get("coverage")) or 0) < 1
    ]
    if partial:
        warnings.append(f"{'、'.join(partial)}存在缺项，观察分按可用指标重加权")

    history_count = len(_metrics._history_values(turnover_history))
    if 0 < history_count < 20:
        warnings.append(f"成交额相对基线仅有 {history_count} 个历史交易日")
    return warnings


def _status_label(
    heat_score: float | None, fragility_score: float | None, confidence: float
) -> str:
    if heat_score is None or confidence < 0.35:
        return "数据不足"
    fragile = fragility_score is not None and fragility_score >= 55
    if heat_score >= 70:
        return "升温但脆弱" if fragile else "偏热"
    if heat_score >= 55:
        return "结构活跃但脆弱" if fragile else "温和活跃"
    if heat_score >= 40:
        return "结构分化且脆弱" if fragile else "中性偏冷"
    return "偏冷且脆弱" if fragile else "偏冷"


def build_market_temperature(
    trade_date: str,
    *,
    overview: Mapping[str, Any] | None,
    indices: Any,
    limits: Mapping[str, Any] | None,
    moneyflow: Mapping[str, Any] | None,
    industries: Any,
    turnover_history: Any,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the six-dimensional market-temperature observation.

    The function is intentionally tolerant of partial inputs.  An unavailable
    dimension receives ``score=None``; available dimensions are reweighted for
    the composite and the reduced coverage is reflected in ``confidence``.
    """
    overview = overview or {}
    limits = limits or {}
    moneyflow = moneyflow or {}

    metrics: dict[str, float | None] = {}
    metrics.update(_metrics._turnover_metrics(overview, turnover_history))
    metrics.update(_metrics._breadth_metrics(overview))
    metrics.update(_metrics._tail_metrics(overview, limits))
    metrics.update(_metrics._index_metrics(indices))
    metrics.update(_metrics._industry_metrics(industries))
    metrics.update(_metrics._moneyflow_metrics(moneyflow))
    metrics = {key: _metrics._rounded(value) for key, value in metrics.items()}

    dimensions = _build_dimensions(metrics)
    heat_score = _composite_heat(dimensions)
    fragility_score = _fragility_score(dimensions, metrics)
    tensions = build_core_tensions(dimensions, metrics)
    validation = build_validation_conditions(str(trade_date), tensions, metrics)
    prior_conditions = previous.get("validation_conditions") if previous else None
    previous_validation = evaluate_conditions(prior_conditions, metrics)
    confidence = _confidence(
        dimensions,
        overview=overview,
        indices=indices,
        limits=limits,
        moneyflow=moneyflow,
        industries=industries,
        turnover_history=turnover_history,
    )
    data_warnings = _data_warnings(
        dimensions,
        limits=limits,
        turnover_history=turnover_history,
    )

    return {
        "trade_date": str(trade_date),
        "calibration": CALIBRATION,
        "position_mapping": None,
        "heat_score": heat_score,
        "fragility_score": fragility_score,
        "status_label": _status_label(heat_score, fragility_score, confidence),
        "dimensions": dimensions,
        "core_tensions": tensions,
        "validation_conditions": validation,
        "previous_validation": previous_validation,
        "metrics": metrics,
        "confidence": confidence,
        "data_warnings": data_warnings,
    }
