"""State-panel constants and derivation for dashboard payloads.

Depends only on :mod:`payload_helpers`. Functions here build the risk-appetite
state panel from free local sources when no explicit panel file is supplied.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .payload_helpers import (
    STATE_COLUMNS,
    PanelDocument,
    _as_list,
    _as_mapping,
    _coerce_row_value,
    _first_present,
    _number,
    _rounded,
    _theme_valuation_average,
)

STATE_PANEL_ENV = "MARKET_STATE_PANEL"
DEFAULT_STATE_PANEL_NAME = "market_state_panel.csv"


def _resolve_state_panel_path(state_panel_path: Path | None, out_dir: Path) -> Path | None:
    if state_panel_path is not None:
        return state_panel_path
    env_value = os.getenv(STATE_PANEL_ENV)
    if env_value:
        return Path(env_value)
    default_path = out_dir / DEFAULT_STATE_PANEL_NAME
    return default_path if default_path.exists() else None


def _read_state_panel(state_panel_path: Path | None, out_dir: Path) -> PanelDocument:
    panel_path = _resolve_state_panel_path(state_panel_path, out_dir)
    if panel_path is None:
        return PanelDocument(path=None, exists=False, rows=[])
    if not panel_path.exists():
        return PanelDocument(
            path=panel_path,
            exists=False,
            rows=[],
            error=f"未找到状态面板：{panel_path}",
        )
    try:
        with panel_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = [
                {str(key): _coerce_row_value(value) for key, value in row.items() if key}
                for row in reader
            ]
    except OSError as exc:
        return PanelDocument(path=panel_path, exists=True, rows=[], error=str(exc))
    return PanelDocument(path=panel_path, exists=True, rows=rows)


def _score_label(value: float | None) -> str:
    if value is None:
        return "暂不可用"
    if value >= 70:
        return "风险偏好较强"
    if value >= 45:
        return "中性"
    return "风险偏好较弱"


def _participation_label(value: float | None) -> str:
    if value is None:
        return "暂不可用"
    if value >= 0.03:
        return "参与度较高"
    if value >= -0.03:
        return "参与度分化"
    return "少数资产领涨"


def _valuation_label(value: float | None) -> str:
    if value is None:
        return "暂不可用"
    if value >= 1.0:
        return "估值压力偏高"
    if value <= -1.0:
        return "估值压力缓和"
    return "估值状态均衡"


def _latest_panel_row(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    for row in reversed(rows):
        if any(_number(row.get(column)) is not None for column in STATE_COLUMNS):
            return row
    return {}


def _macro_value(snapshot: Mapping[str, Any], symbol: str) -> float | None:
    macros = _as_mapping(snapshot.get("macros"))
    payload = _as_mapping(macros.get(symbol))
    return _rounded(payload.get("close"))


def _stock_value(snapshot: Mapping[str, Any], symbol: str) -> float | None:
    stocks = _as_mapping(snapshot.get("us_stocks"))
    payload = _as_mapping(stocks.get(symbol))
    return _rounded(payload.get("close"))


def _stock_pct_change(snapshot: Mapping[str, Any], symbol: str) -> float | None:
    stocks = _as_mapping(snapshot.get("us_stocks"))
    payload = _as_mapping(stocks.get(symbol))
    return _rounded(payload.get("pct_chg"))


def _index_value(raw_market: Mapping[str, Any], symbol: str) -> float | None:
    market = _as_mapping(raw_market.get("market"))
    for item in _as_list(market.get("indices")):
        entry = _as_mapping(item)
        if entry.get("symbol") == symbol:
            return _rounded(entry.get("close"))
    return None


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _score_from_vix(vix: float) -> float:
    return _clamp(100 - (vix - 10) * 3.0, 0, 100)


def _score_from_put_call(ratio: float) -> float:
    return _clamp(50 - (ratio - 0.75) * 100, 0, 100)


def _score_from_aaii_spread(spread: float) -> float:
    return _clamp(50 + spread, 0, 100)


def _aaii_spread(raw_market: Mapping[str, Any], snapshot: Mapping[str, Any]) -> float | None:
    sentiment = _as_mapping(raw_market.get("sentiment"))
    aaii = _as_mapping(_first_present(sentiment.get("aaii"), snapshot.get("aaii_sentiment")))
    spread = _number(aaii.get("bull_bear_spread"))
    if spread is not None:
        return spread
    bullish = _number(aaii.get("bullish_pct"))
    bearish = _number(aaii.get("bearish_pct"))
    if bullish is None or bearish is None:
        return None
    return bullish - bearish


def _participation_proxy(snapshot: Mapping[str, Any]) -> tuple[float, str] | None:
    rsp_pct = _stock_pct_change(snapshot, "RSP")
    spy_pct = _stock_pct_change(snapshot, "SPY")
    if rsp_pct is not None and spy_pct is not None:
        return round((rsp_pct - spy_pct) / 100, 4), "RSP/SPY"
    qqq_pct = _stock_pct_change(snapshot, "QQQ")
    if spy_pct is not None and qqq_pct is not None:
        return round((spy_pct - qqq_pct) / 100, 4), "SPY/QQQ"
    return None


def _build_risk_block(
    vix: float | None,
    raw_market: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, object]:
    """Compute the risk-appetite related fields for a derived state-panel row."""
    updates: dict[str, object] = {}
    risk_components: list[float] = []
    if vix is not None:
        risk_components.append(_score_from_vix(vix))
    sentiment = _as_mapping(raw_market.get("sentiment"))
    put_call = _as_mapping(sentiment.get("put_call"))
    put_call_ratio = _number(_first_present(put_call.get("equity"), put_call.get("total")))
    if put_call_ratio is not None:
        updates["put_call_ratio"] = round(put_call_ratio, 4)
        risk_components.append(_score_from_put_call(put_call_ratio))
    spread = _aaii_spread(raw_market, snapshot)
    if spread is not None:
        updates["aaii_bull_bear_spread"] = round(spread, 2)
        risk_components.append(_score_from_aaii_spread(spread))
    if risk_components:
        updates["own_risk_appetite_score"] = round(sum(risk_components) / len(risk_components), 2)
        updates["own_risk_appetite_component_count"] = len(risk_components)
    return updates


def _build_valuation_block(
    scores: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    ten_year: float | None,
) -> dict[str, object]:
    """Compute the valuation-rate-gap related fields for a derived state-panel row."""
    updates: dict[str, object] = {}
    valuation_components: list[float] = []
    theme_valuation = _theme_valuation_average(scores)
    if theme_valuation is not None:
        valuation_components.append(_clamp((50 - theme_valuation) / 25, -2, 2))
    if ten_year is not None:
        valuation_components.append(_clamp((ten_year - 4.0) / 1.5, -2, 2))
    if valuation_components:
        updates["valuation_rate_gap_proxy"] = round(
            sum(valuation_components) / len(valuation_components), 2
        )
        updates["valuation_rate_gap_component_count"] = len(valuation_components)
    return updates


def _build_price_block(
    raw_market: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, object]:
    """Compute the price-level fields (SPY / SPX closes) for a derived state-panel row."""
    updates: dict[str, object] = {}
    spy_close = _stock_value(snapshot, "SPY")
    if spy_close is not None:
        updates["spy_close"] = spy_close
    sp500_close = _index_value(raw_market, "SPX")
    if sp500_close is not None:
        updates["sp500_close"] = sp500_close
    return updates


def _derived_state_panel_row(
    scores: Mapping[str, Any],
    raw_market: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, object] | None:
    row: dict[str, object] = {}
    date_value = _first_present(scores.get("date"), raw_market.get("date"), snapshot.get("date"))
    if date_value:
        row["date"] = str(date_value)

    vix = _rounded(_first_present(_macro_value(snapshot, "^VIX"), _macro_value(snapshot, "VIX")))
    if vix is not None:
        row["vix"] = vix

    row.update(_build_risk_block(vix, raw_market, snapshot))

    participation = _participation_proxy(snapshot)
    if participation is not None:
        row["rsp_spy_participation_proxy"], row["rsp_spy_participation_proxy_source"] = (
            participation
        )

    ten_year = _macro_value(snapshot, "^TNX")
    if ten_year is not None:
        row["ten_year_yield"] = ten_year
    row.update(_build_valuation_block(scores, snapshot, ten_year))
    row.update(_build_price_block(raw_market, snapshot))

    if not any(_number(row.get(column)) is not None for column in STATE_COLUMNS):
        return None
    row["state_panel_source"] = "auto_free_source_proxy"
    return row


def _ensure_state_panel(
    panel: PanelDocument,
    scores: Mapping[str, Any],
    raw_market: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> PanelDocument:
    if panel.rows:
        return panel
    derived_row = _derived_state_panel_row(scores, raw_market, snapshot)
    if derived_row is None:
        return panel
    return PanelDocument(
        path=panel.path,
        exists=panel.exists or panel.path is None,
        rows=[derived_row],
        error=panel.error,
    )


def _panel_is_derived(panel: PanelDocument) -> bool:
    return panel.path is None and panel.exists and bool(panel.rows)


def _state_panel_source_label(panel: PanelDocument) -> str:
    if _panel_is_derived(panel):
        return "自动免费来源代理（Cboe/FRED VIX / Cboe Put/Call / AAII / SPY-QQQ / 主题估值）"
    return "本地状态面板"
