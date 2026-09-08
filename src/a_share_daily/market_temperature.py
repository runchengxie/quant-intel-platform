"""Pure, provisional market-temperature calculations.

The module deliberately performs no I/O.  It consumes the aggregates already
produced by :mod:`a_share_daily.review` (or equivalent dictionaries) and keeps
the scoring scale observational: only returns, participation ratios, and
values relative to their own history enter a score.

``heat_score`` is descriptive, not a position recommendation.  In particular,
the loss-risk dimension has the opposite polarity to the other five dimensions
and is inverted only when the composite heat score is calculated.

This module is now a thin re-export layer.  The numeric helpers and
``_*_metrics`` functions live in :mod:`a_share_daily.temperature_metrics`, while
the dimension assembly and the public :func:`build_market_temperature` entry
point live in :mod:`a_share_daily.temperature_dimensions`.  Everything is
re-exported here so that ``from a_share_daily.market_temperature import ...``
and ``from a_share_daily import market_temperature as mt`` keep working.
"""

from __future__ import annotations

from .market_temperature_signals import (
    build_core_tensions,
    build_validation_conditions,
    evaluate_conditions,
)
from .temperature_dimensions import (
    _DIMENSION_WEIGHTS,
    CALIBRATION,
    _build_dimensions,
    _composite_heat,
    _confidence,
    _data_warnings,
    _dimension,
    _fragility_score,
    _participation_dimensions,
    _risk_and_trend_dimensions,
    _rotation_dimensions,
    _status_label,
    build_market_temperature,
)
from .temperature_metrics import (
    _breadth_metrics,
    _clamp,
    _failed_limit_count,
    _first_number,
    _first_ratio,
    _history_values,
    _index_metrics,
    _industry_metrics,
    _industry_return,
    _limit_count,
    _mean,
    _moneyflow_metrics,
    _number,
    _pct_return,
    _ratio,
    _records,
    _rounded,
    _score_between,
    _stock_total,
    _tail_metrics,
    _turnover_metrics,
)

__all__ = [
    "CALIBRATION",
    "build_core_tensions",
    "build_validation_conditions",
    "evaluate_conditions",
    "_DIMENSION_WEIGHTS",
    "_number",
    "_clamp",
    "_ratio",
    "_pct_return",
    "_score_between",
    "_mean",
    "_rounded",
    "_first_number",
    "_first_ratio",
    "_records",
    "_history_values",
    "_turnover_metrics",
    "_breadth_metrics",
    "_stock_total",
    "_limit_count",
    "_failed_limit_count",
    "_tail_metrics",
    "_index_metrics",
    "_industry_return",
    "_industry_metrics",
    "_moneyflow_metrics",
    "_dimension",
    "_participation_dimensions",
    "_risk_and_trend_dimensions",
    "_rotation_dimensions",
    "_build_dimensions",
    "_composite_heat",
    "_fragility_score",
    "_confidence",
    "_data_warnings",
    "_status_label",
    "build_market_temperature",
]
