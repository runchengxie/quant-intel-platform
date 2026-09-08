"""Aggregation builders for dashboard payloads.

Depends on :mod:`payload_helpers` (constants + numeric helpers) and
:mod:`payload_state` (state-panel rows and labels). Produces the latest-state
summary, chart rows, similar-state neighbors, theme/coverage tables and a share
snapshot that the top-level :func:`build_payload` assembles.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

from .payload_helpers import (
    CHART_COLUMNS,
    CHART_ROW_LIMIT,
    FORWARD_RETURN_COLUMNS,
    NEIGHBOR_LIMIT,
    STATE_COLUMNS,
    PanelDocument,
    _as_list,
    _as_mapping,
    _first_present,
    _number,
    _rounded,
)
from .payload_state import (
    _index_value,
    _latest_panel_row,
    _macro_value,
    _participation_label,
    _score_label,
    _stock_value,
    _valuation_label,
)


def _latest_payload(
    scores: Mapping[str, Any],
    raw_market: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    panel: PanelDocument,
) -> dict[str, object]:
    latest_row = _latest_panel_row(panel.rows)
    risk = _rounded(latest_row.get("own_risk_appetite_score"))
    participation = _rounded(latest_row.get("rsp_spy_participation_proxy"), 4)
    valuation_gap = _rounded(latest_row.get("valuation_rate_gap_proxy"))
    vix = _rounded(_first_present(latest_row.get("vix"), _macro_value(snapshot, "^VIX")))
    spy_close = _rounded(_first_present(latest_row.get("spy_close"), _stock_value(snapshot, "SPY")))
    sp500_close = _rounded(
        _first_present(latest_row.get("sp500_close"), _index_value(raw_market, "SPX"))
    )
    ten_year = _rounded(
        _first_present(latest_row.get("ten_year_yield"), _macro_value(snapshot, "^TNX"))
    )
    hy_oas = _rounded(latest_row.get("hy_oas"))
    date_value = _first_present(
        latest_row.get("date"),
        scores.get("date"),
        raw_market.get("date"),
        snapshot.get("date"),
    )
    return {
        "date": str(date_value or "unknown"),
        "riskAppetite": risk,
        "riskAppetiteLabel": _score_label(risk),
        "participation": participation,
        "participationLabel": _participation_label(participation),
        "valuationRateGap": valuation_gap,
        "valuationRateGapLabel": _valuation_label(valuation_gap),
        "vix": vix,
        "spyClose": spy_close,
        "sp500Close": sp500_close,
        "tenYearYield": ten_year,
        "hyOas": hy_oas,
        "componentCount": _rounded(latest_row.get("own_risk_appetite_component_count"), 0),
        "valuationComponentCount": _rounded(
            latest_row.get("valuation_rate_gap_component_count"), 0
        ),
    }


def _chart_rows(panel: PanelDocument) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in panel.rows[-CHART_ROW_LIMIT:]:
        date_value = row.get("date")
        if not date_value:
            continue
        chart_row: dict[str, object] = {"date": str(date_value)}
        has_value = False
        for column in CHART_COLUMNS:
            value = _rounded(row.get(column), 4 if column.endswith("proxy") else 2)
            chart_row[column] = value
            has_value = has_value or value is not None
        if has_value:
            rows.append(chart_row)
    return rows


def _standard_deviations(rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    deviations: dict[str, float] = {}
    for column in STATE_COLUMNS:
        values = [_number(row.get(column)) for row in rows]
        clean_values = [value for value in values if value is not None]
        if len(clean_values) < 2:
            continue
        deviation = statistics.pstdev(clean_values)
        if deviation > 0:
            deviations[column] = deviation
    return deviations


def _similar_state_neighbors(panel: PanelDocument) -> list[dict[str, object]]:
    if len(panel.rows) < 3:
        return []
    latest_row = _latest_panel_row(panel.rows)
    if not latest_row:
        return []
    target: dict[str, float] = {}
    for column in STATE_COLUMNS:
        target_value = _number(latest_row.get(column))
        if target_value is not None:
            target[column] = target_value
    if len(target) < 2:
        return []
    latest_date = latest_row.get("date")
    deviations = _standard_deviations(panel.rows)
    candidates: list[tuple[float, Mapping[str, object]]] = []
    for row in panel.rows:
        if latest_date and row.get("date") == latest_date:
            continue
        distance_terms: list[float] = []
        for column, target_value in target.items():
            current_value = _number(row.get(column))
            deviation = deviations.get(column)
            if current_value is None or deviation is None:
                continue
            distance_terms.append(((current_value - target_value) / deviation) ** 2)
        if len(distance_terms) < 2:
            continue
        distance = math.sqrt(sum(distance_terms) / len(distance_terms))
        candidates.append((distance, row))
    neighbors: list[dict[str, object]] = []
    for distance, row in sorted(candidates, key=lambda item: item[0])[:NEIGHBOR_LIMIT]:
        entry: dict[str, object] = {
            "date": str(row.get("date", "")),
            "distance": round(distance, 3),
            "riskAppetite": _rounded(row.get("own_risk_appetite_score")),
            "participation": _rounded(row.get("rsp_spy_participation_proxy"), 4),
            "valuationRateGap": _rounded(row.get("valuation_rate_gap_proxy")),
            "vix": _rounded(row.get("vix")),
        }
        for column, label in FORWARD_RETURN_COLUMNS:
            entry[f"forwardReturn{label}"] = _rounded(row.get(column), 4)
        neighbors.append(entry)
    return neighbors


def _average(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _median(values: Sequence[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def _neighbor_summary(neighbors: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for _, label in FORWARD_RETURN_COLUMNS:
        key = f"forwardReturn{label}"
        values = [_number(row.get(key)) for row in neighbors]
        clean_values = [value for value in values if value is not None]
        if not clean_values:
            continue
        positive_count = sum(1 for value in clean_values if value > 0)
        summary.append(
            {
                "horizon": label,
                "count": len(clean_values),
                "average": _average(clean_values),
                "median": _median(clean_values),
                "positiveRate": round(positive_count / len(clean_values), 4),
            }
        )
    return summary


def _theme_cards(scores: Mapping[str, Any]) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for item in _as_list(scores.get("themes")):
        theme = _as_mapping(item)
        if not theme:
            continue
        breakdown = _as_mapping(theme.get("breakdown"))
        breakdown_rows = [
            {"name": str(name), "value": _rounded(value)}
            for name, value in breakdown.items()
            if _number(value) is not None
        ]
        cards.append(
            {
                "name": str(theme.get("name", "")),
                "label": str(theme.get("label", theme.get("name", "Theme"))),
                "total": _rounded(theme.get("total")),
                "delta": _rounded(_as_mapping(theme.get("meta")).get("delta")),
                "degraded": bool(theme.get("degraded")),
                "breakdown": breakdown_rows,
            }
        )
    return sorted(cards, key=lambda card: _number(card.get("total")) or -1, reverse=True)


def _action_items(actions: Mapping[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in _as_list(actions.get("items")):
        action = _as_mapping(item)
        if not action:
            continue
        items.append(
            {
                "action": str(action.get("action", "")),
                "name": str(action.get("name", "")),
                "reason": str(action.get("reason", "")),
            }
        )
    return items


def _market_table(payload: Mapping[str, Any], key: str, limit: int = 12) -> list[dict[str, object]]:
    node = _as_mapping(payload.get(key))
    rows: list[dict[str, object]] = []
    for symbol, raw in node.items():
        entry = _as_mapping(raw)
        rows.append(
            {
                "symbol": str(symbol),
                "label": str(entry.get("label", symbol)),
                "close": _rounded(entry.get("close")),
                "pctChg": _rounded(entry.get("pct_chg")),
                "source": str(entry.get("source", "")),
            }
        )
    return sorted(rows, key=lambda row: abs(_number(row.get("pctChg")) or 0), reverse=True)[:limit]


def _lead_lag_rows(snapshot: Mapping[str, Any], limit: int = 14) -> list[dict[str, object]]:
    raw_rows = _as_list(snapshot.get("global_lead_lag")) or _as_list(
        snapshot.get("concept_mapping")
    )
    rows: list[dict[str, object]] = []
    for item in raw_rows:
        entry = _as_mapping(item)
        if not entry:
            continue
        rows.append(
            {
                "concept": str(entry.get("concept", "")),
                "avgPctChg": _rounded(entry.get("avg_pct_chg")),
                "signal": str(entry.get("signal", "")),
                "drivers": [str(driver) for driver in _as_list(entry.get("drivers"))[:4]],
            }
        )
    return sorted(rows, key=lambda row: abs(_number(row.get("avgPctChg")) or 0), reverse=True)[
        :limit
    ]


def _a_share_snapshot(tushare: Mapping[str, Any]) -> dict[str, object]:
    breadth = _as_mapping(tushare.get("breadth"))
    moneyflow = _as_mapping(tushare.get("moneyflow"))
    limit_list = _as_mapping(tushare.get("limit_list"))
    indices = _as_mapping(tushare.get("indices"))
    index_rows: list[dict[str, object]] = []
    for code, raw in indices.items():
        entry = _as_mapping(raw)
        index_rows.append(
            {
                "code": str(code),
                "name": str(entry.get("name", code)),
                "close": _rounded(entry.get("close")),
                "pctChg": _rounded(entry.get("pct_chg")),
            }
        )
    top_moneyflow: list[dict[str, object]] = []
    for item in _as_list(moneyflow.get("top_entries"))[:8]:
        entry = _as_mapping(item)
        top_moneyflow.append(
            {
                "name": str(entry.get("name", entry.get("ts_code", ""))),
                "code": str(entry.get("ts_code", "")),
                "netAmount": _rounded(entry.get("net_mf_amount")),
            }
        )
    return {
        "tradeDate": str(tushare.get("trade_date", "")),
        "generatedAt": str(tushare.get("generated_at", "")),
        "breadth": {
            "upCount": _rounded(breadth.get("up_count"), 0),
            "downCount": _rounded(breadth.get("down_count"), 0),
            "upPct": _rounded(breadth.get("up_pct")),
            "downPct": _rounded(breadth.get("down_pct")),
            "avgPctChg": _rounded(breadth.get("avg_pct_chg")),
            "medianPctChg": _rounded(breadth.get("median_pct_chg")),
        },
        "indices": sorted(
            index_rows, key=lambda row: abs(_number(row.get("pctChg")) or 0), reverse=True
        )[:8],
        "moneyflow": {
            "netAmount": _rounded(moneyflow.get("total_net_mf_amount")),
            "topEntries": top_moneyflow,
        },
        "limitList": {
            "upCount": len(_as_list(limit_list.get("up"))),
            "downCount": len(_as_list(limit_list.get("down"))),
            "unavailable": bool(limit_list.get("_unavailable")),
        },
    }


def _etl_source_rows(status: Mapping[str, Any]) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    for item in _as_list(status.get("sources")):
        entry = _as_mapping(item)
        if not entry:
            continue
        sources.append(
            {
                "name": str(entry.get("name", "")),
                "ok": bool(entry.get("ok")),
                "message": str(entry.get("message", "")),
            }
        )
    return sources


def _latest_panel_value(panel: PanelDocument, *columns: str, digits: int = 2) -> float | None:
    row = _latest_panel_row(panel.rows)
    for column in columns:
        value = _rounded(row.get(column), digits)
        if value is not None:
            return value
    return None


def _volatility_structure(snapshot: Mapping[str, Any]) -> float | None:
    macros = _as_mapping(snapshot.get("macros"))
    vix = _number(_as_mapping(macros.get("^VIX")).get("close"))
    vvix = _number(
        _first_present(
            _as_mapping(macros.get("^VVIX")).get("close"),
            _as_mapping(macros.get("VVIX")).get("close"),
        )
    )
    if vix is None or vvix is None or vix == 0:
        return None
    return round(vvix / vix / 3.5, 4)
