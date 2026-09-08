"""Pure metric helpers for market-temperature calculations.

See :mod:`a_share_daily.market_temperature` for the module-level contract. This
submodule holds the low-level numeric helpers and the ``_*_metrics`` functions
that turn raw aggregates into plain float-or-``None`` metric dicts.  The
dimension-level logic lives in :mod:`a_share_daily.temperature_dimensions`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from statistics import median
from typing import Any

CALIBRATION = "provisional_observation_scale"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def _ratio(value: Any) -> float | None:
    """Read a proportion expressed as either 0..1 or 0..100."""
    number = _number(value)
    if number is None:
        return None
    if abs(number) > 1:
        number /= 100.0
    return number


def _pct_return(value: Any) -> float | None:
    """Read a field whose public contract is percentage points."""
    number = _number(value)
    return None if number is None else number / 100.0


def _score_between(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    if high <= low:
        raise ValueError("high must be greater than low")
    return round(100.0 * _clamp((value - low) / (high - low)), 1)


def _mean(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _rounded(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _first_ratio(*values: Any) -> float | None:
    for value in values:
        parsed = _ratio(value)
        if parsed is not None:
            return parsed
    return None


def _records(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            records = value.to_dict("records")
            if isinstance(records, list):
                return [row for row in records if isinstance(row, Mapping)]
        except (TypeError, ValueError):
            pass
    if isinstance(value, Mapping):
        if all(isinstance(item, Mapping) for item in value.values()):
            return [item for item in value.values() if isinstance(item, Mapping)]
        if all(_number(item) is not None for item in value.values()):
            return [{"avg_pct_chg": item} for item in value.values()]
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _history_values(turnover_history: Any) -> list[float]:
    if isinstance(turnover_history, Mapping):
        for key in ("values", "turnover", "turnover_total", "history"):
            if key in turnover_history:
                return _history_values(turnover_history[key])
        candidates = turnover_history.values()
    elif isinstance(turnover_history, Sequence) and not isinstance(turnover_history, (str, bytes)):
        candidates = turnover_history
    else:
        return []

    values: list[float] = []
    for item in candidates:
        if isinstance(item, Mapping):
            item = next(
                (
                    item[key]
                    for key in ("turnover_total", "turnover", "amount", "value")
                    if key in item
                ),
                None,
            )
        number = _number(item)
        if number is not None and number > 0:
            values.append(number)
    return values


def _turnover_metrics(
    overview: Mapping[str, Any], turnover_history: Any
) -> dict[str, float | None]:
    current = _first_number(
        overview.get("turnover_total"), overview.get("turnover"), overview.get("amount")
    )
    history = _history_values(turnover_history)
    if current is None or current <= 0 or len(history) < 3:
        return {"turnover_vs_median": None, "turnover_percentile": None}
    history_median = median(history)
    if history_median <= 0:
        return {"turnover_vs_median": None, "turnover_percentile": None}
    percentile = sum(value <= current for value in history) / len(history)
    return {
        "turnover_vs_median": current / history_median,
        "turnover_percentile": percentile,
    }


def _breadth_metrics(overview: Mapping[str, Any]) -> dict[str, float | None]:
    breadth_value = overview.get("breadth")
    breadth: Mapping[str, Any] = breadth_value if isinstance(breadth_value, Mapping) else {}
    total = _first_number(breadth.get("total"), overview.get("total_stocks"))
    up = _first_number(breadth.get("up"), overview.get("up_count"))
    up_ratio = _first_ratio(breadth.get("up_ratio"), overview.get("breadth_up_ratio"))
    if up_ratio is None and up is not None and total and total > 0:
        up_ratio = up / total
    return {
        "breadth_up_ratio": up_ratio,
        "median_return": _pct_return(overview.get("median_pct_chg")),
        "turnover_weighted_return": _pct_return(overview.get("wavg_pct_chg")),
        "vwap_above_ratio": _first_ratio(
            overview.get("vwap_above_ratio"), overview.get("above_vwap_ratio")
        ),
    }


def _stock_total(overview: Mapping[str, Any]) -> float | None:
    breadth_value = overview.get("breadth")
    breadth: Mapping[str, Any] = breadth_value if isinstance(breadth_value, Mapping) else {}
    total = _first_number(breadth.get("total"), overview.get("total_stocks"))
    return total if total is not None and total > 0 else None


def _limit_count(limits: Mapping[str, Any], side: str) -> float | None:
    nested = limits.get(side)
    if isinstance(nested, Mapping):
        nested = nested.get("count")
    prefix = "limit_up" if side == "limit_up" else "limit_down"
    alternatives = (
        nested,
        limits.get(f"{prefix}_count"),
        limits.get("exact_down_limit_count") if side == "limit_down" else None,
        limits.get("down_limit_count") if side == "limit_down" else None,
    )
    # Deliberately do not consume overview.down_limit_approx or similarly named
    # heuristic fields: mixed 5/10/20/30% boards make that count non-comparable.
    return _first_number(*alternatives)


def _failed_limit_count(limits: Mapping[str, Any]) -> float | None:
    direct = _first_number(
        limits.get("failed_limit_up_count"),
        limits.get("failed_board_count"),
        limits.get("failed_count"),
    )
    if direct is not None:
        return direct
    breakdown = limits.get("status_breakdown")
    if not isinstance(breakdown, Mapping):
        return None
    failed = 0.0
    found = False
    for key, value in breakdown.items():
        if any(token in str(key).lower() for token in ("炸", "开板", "failed")):
            number = _number(value)
            if number is not None:
                failed += number
                found = True
    return failed if found else None


def _tail_metrics(
    overview: Mapping[str, Any], limits: Mapping[str, Any]
) -> dict[str, float | None]:
    total = _stock_total(overview)
    up_count = _limit_count(limits, "limit_up")
    down_count = _limit_count(limits, "limit_down")
    up5_count = _first_number(overview.get("up5_count"), overview.get("up_5_count"))
    down5_count = _first_number(overview.get("down5_count"), overview.get("down_5_count"))

    up_ratio = _first_ratio(limits.get("limit_up_ratio"))
    down_ratio = _first_ratio(limits.get("limit_down_ratio"))
    if total is not None:
        up_ratio = (
            up_ratio
            if up_ratio is not None
            else (up_count / total if up_count is not None else None)
        )
        down_ratio = (
            down_ratio
            if down_ratio is not None
            else (down_count / total if down_count is not None else None)
        )

    failed = _failed_limit_count(limits)
    seal_rate = _first_ratio(limits.get("seal_rate"), limits.get("limit_up_seal_rate"))
    if seal_rate is None and up_count is not None and failed is not None and up_count + failed > 0:
        seal_rate = up_count / (up_count + failed)

    return {
        "limit_up_ratio": up_ratio,
        "up5_ratio": up5_count / total if up5_count is not None and total else None,
        "seal_rate": seal_rate,
        "limit_down_ratio": down_ratio,
        "down5_ratio": down5_count / total if down5_count is not None and total else None,
        "failed_board_ratio": 1 - seal_rate if seal_rate is not None else None,
    }


def _index_metrics(indices: Any) -> dict[str, float | None]:
    direct = indices if isinstance(indices, Mapping) else {}
    direct_positive = _first_ratio(direct.get("index_positive_ratio"))
    direct_median = _number(direct.get("index_median_return"))
    direct_close = _first_ratio(direct.get("index_close_position"))
    if direct_positive is not None or direct_median is not None or direct_close is not None:
        return {
            "index_positive_ratio": direct_positive,
            "index_median_return": direct_median,
            "index_close_position": direct_close,
        }

    returns: list[float] = []
    close_positions: list[float] = []
    for row in _records(indices):
        pct_change = _pct_return(row.get("pct_chg"))
        if pct_change is None:
            close = _number(row.get("close"))
            previous_close = _number(row.get("pre_close"))
            if close is not None and previous_close and previous_close > 0:
                pct_change = close / previous_close - 1
        if pct_change is not None:
            returns.append(pct_change)

        high = _number(row.get("high"))
        low = _number(row.get("low"))
        close = _number(row.get("close"))
        if high is not None and low is not None and close is not None and high > low:
            close_positions.append(_clamp((close - low) / (high - low)))

    return {
        "index_positive_ratio": (
            sum(value > 0 for value in returns) / len(returns) if returns else None
        ),
        "index_median_return": median(returns) if returns else None,
        "index_close_position": _mean(close_positions),
    }


def _industry_return(row: Mapping[str, Any]) -> float | None:
    for key in ("avg_pct_chg", "median_pct_chg", "pct_chg", "pct_change"):
        if key in row:
            return _pct_return(row[key])
    return _number(row.get("return"))


def _industry_metrics(industries: Any) -> dict[str, float | None]:
    if isinstance(industries, Mapping):
        positive_ratio = _first_ratio(
            industries.get("industry_positive_ratio"), industries.get("positive_ratio")
        )
        median_return = _number(industries.get("industry_median_return"))
        concentration = _first_ratio(industries.get("leadership_concentration"))
        if positive_ratio is not None or median_return is not None or concentration is not None:
            return {
                "industry_positive_ratio": positive_ratio,
                "industry_median_return": median_return,
                "leadership_concentration": concentration,
            }

    returns = [
        value for row in _records(industries) if (value := _industry_return(row)) is not None
    ]
    if len(returns) < 3:
        return {
            "industry_positive_ratio": None,
            "industry_median_return": None,
            "leadership_concentration": None,
        }
    positive = sorted((value for value in returns if value > 0), reverse=True)
    concentration = None
    if positive and sum(positive) > 0:
        concentration = sum(positive[:3]) / sum(positive)
    return {
        "industry_positive_ratio": sum(value > 0 for value in returns) / len(returns),
        "industry_median_return": median(returns),
        "leadership_concentration": concentration,
    }


def _moneyflow_metrics(moneyflow: Mapping[str, Any]) -> dict[str, float | None]:
    flow = moneyflow.get("moneyflow")
    if not isinstance(flow, Mapping):
        flow = moneyflow
    inflow_stocks = _first_number(flow.get("inflow_stocks"), flow.get("positive_stocks"))
    outflow_stocks = _first_number(flow.get("outflow_stocks"), flow.get("negative_stocks"))
    positive_ratio = None
    if (
        inflow_stocks is not None
        and outflow_stocks is not None
        and inflow_stocks + outflow_stocks > 0
    ):
        positive_ratio = inflow_stocks / (inflow_stocks + outflow_stocks)

    net_in = _first_number(flow.get("net_in"), flow.get("gross_inflow"))
    net_out = _first_number(flow.get("net_out"), flow.get("gross_outflow"))
    balance_ratio = _first_ratio(flow.get("flow_balance_ratio"), flow.get("net_flow_ratio"))
    if balance_ratio is None and net_in is not None and net_out is not None:
        gross = abs(net_in) + abs(net_out)
        if gross > 0:
            balance_ratio = (net_in + net_out) / gross
    return {
        "flow_positive_stock_ratio": positive_ratio,
        "flow_balance_ratio": balance_ratio,
    }
