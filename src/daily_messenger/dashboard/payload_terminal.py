"""Terminal metric-card builders for dashboard payloads.

Depends on :mod:`payload_helpers`, :mod:`payload_state` and
:mod:`payload_aggregations`. Produces the market-panorama terminal cards
(sentiment / valuation / drawdown / events) consumed by ``build_payload``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .payload_aggregations import (
    _latest_panel_value,
    _volatility_structure,
)
from .payload_helpers import (
    PanelDocument,
    _as_list,
    _as_mapping,
    _first_present,
    _number,
    _rounded,
    _theme_valuation_average,
)
from .payload_state import (
    _latest_panel_row,
    _panel_is_derived,
    _state_panel_source_label,
    _stock_pct_change,
    _stock_value,
)


def _metric_card(
    *,
    key: str,
    label: str,
    value: float | None,
    status: str,
    detail: str,
    unit: str = "",
    source: str = "",
    ref_ids: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "status": status,
        "detail": detail,
        "source": source,
        "refIds": list(ref_ids),
    }


def _terminal_sentiment_cards(
    latest: Mapping[str, Any],
    cross_market: Mapping[str, Any],
    panel: PanelDocument,
) -> list[dict[str, object]]:
    risk = _number(latest.get("riskAppetite"))
    vix = _number(latest.get("vix"))
    vol_structure = _volatility_structure(cross_market)
    latest_row = _latest_panel_row(panel.rows)
    spx_breadth = _latest_panel_value(panel, "spx_above_50d_pct", "spy_above_50d_pct")
    ndx_breadth = _latest_panel_value(panel, "ndx_above_50d_pct", "qqq_above_50d_pct")
    participation = _number(latest.get("participation"))
    participation_source = str(
        latest_row.get("rsp_spy_participation_proxy_source") or "RSP/SPY 类代理"
    )
    panel_source = _state_panel_source_label(panel)
    risk_detail = (
        "未提供状态面板时，自动用 Cboe/FRED VIX、Cboe Put/Call 和 AAII 生成自建 fear_greed_proxy。"
        if _panel_is_derived(panel)
        else "由本地风险偏好状态面板替代目标站 Fear & Greed。"
    )
    participation_detail = (
        f"当前使用 {participation_source} 当日相对表现作为 ETF 参与度代理，不等同于成分股宽度。"
        if _panel_is_derived(panel)
        else "当前使用 RSP/SPY 类代理观察市场内部参与度。"
    )
    return [
        _metric_card(
            key="fear_greed_proxy",
            label="Fear & Greed 代理",
            value=risk,
            status="proxy" if risk is not None else "missing",
            detail=risk_detail,
            source=f"{panel_source} / 自建风险偏好代理",
        ),
        _metric_card(
            key="vix",
            label="VIX",
            value=vix,
            status="available" if vix is not None else "missing",
            detail="优先使用跨市场快照或状态面板中的 VIX。",
            source="FRED/Cboe 快照链路或本地状态面板",
            ref_ids=("fred-vix", "cboe-vix"),
        ),
        _metric_card(
            key="vol_structure",
            label="VVIX / VIX / 3.5",
            value=vol_structure,
            status="available" if vol_structure is not None else "missing",
            detail="需要跨市场快照同时包含 VVIX 和 VIX。",
            source="Cboe VVIX/VIX 或授权波动率数据",
            ref_ids=("cboe-vix",),
        ),
        _metric_card(
            key="spx_breadth",
            label="SPX 50D 宽度",
            value=spx_breadth,
            status="proxy" if spx_breadth is not None else "missing",
            detail="可选状态面板列；缺失时不使用 A 股宽度冒充。",
            unit="%",
            source="本地状态面板",
        ),
        _metric_card(
            key="ndx_breadth",
            label="NDX 50D 宽度",
            value=ndx_breadth,
            status="proxy" if ndx_breadth is not None else "missing",
            detail="可选状态面板列；缺失时不使用 A 股宽度冒充。",
            unit="%",
            source="本地状态面板",
        ),
        _metric_card(
            key="participation_proxy",
            label="参与度代理",
            value=participation,
            status="proxy" if participation is not None else "missing",
            detail=participation_detail,
            source=panel_source,
        ),
    ]


def _terminal_valuation_cards(
    scores: Mapping[str, Any],
    latest: Mapping[str, Any],
    panel: PanelDocument,
) -> list[dict[str, object]]:
    spx_pe = _latest_panel_value(panel, "spx_ntm_pe", "spy_ntm_pe")
    ndx_pe = _latest_panel_value(panel, "ndx_ntm_pe", "qqq_ntm_pe")
    spx_pct = _latest_panel_value(
        panel, "spx_ntm_pe_percentile", "spx_pe_percentile", "spy_pe_percentile"
    )
    ndx_pct = _latest_panel_value(
        panel, "ndx_ntm_pe_percentile", "ndx_pe_percentile", "qqq_pe_percentile"
    )
    valuation_gap = _number(latest.get("valuationRateGap"))
    theme_valuation = _theme_valuation_average(scores)
    panel_source = _state_panel_source_label(panel)
    valuation_detail = (
        "未提供状态面板时，自动用主题估值因子和 10Y 美债收益率生成估值利率代理。"
        if _panel_is_derived(panel)
        else "本项目已有估值和利率代理状态。"
    )
    return [
        _metric_card(
            key="spx_ntm_pe",
            label="SPX NTM PE",
            value=spx_pe,
            status="proxy" if spx_pe is not None else "missing",
            detail="需要授权估值或本地 valuation panel；当前仅在状态面板提供时展示。",
            source="本地 valuation panel 或授权估值源",
            ref_ids=("factset", "bloomberg", "lseg", "sp-capital-iq"),
        ),
        _metric_card(
            key="spx_pe_percentile",
            label="SPX PE 分位",
            value=spx_pct,
            status="proxy" if spx_pct is not None else "missing",
            detail="目标站展示 1y/5y/10y 分位；这里先接收单列代理分位。",
            unit="%",
            source="本地 valuation panel",
            ref_ids=("factset", "bloomberg", "lseg", "sp-capital-iq"),
        ),
        _metric_card(
            key="ndx_ntm_pe",
            label="NDX NTM PE",
            value=ndx_pe,
            status="proxy" if ndx_pe is not None else "missing",
            detail="需要授权估值或本地 valuation panel；当前仅在状态面板提供时展示。",
            source="本地 valuation panel 或授权估值源",
            ref_ids=("factset", "bloomberg", "lseg", "sp-capital-iq"),
        ),
        _metric_card(
            key="ndx_pe_percentile",
            label="NDX PE 分位",
            value=ndx_pct,
            status="proxy" if ndx_pct is not None else "missing",
            detail="目标站展示 1y/5y/10y 分位；这里先接收单列代理分位。",
            unit="%",
            source="本地 valuation panel",
            ref_ids=("factset", "bloomberg", "lseg", "sp-capital-iq"),
        ),
        _metric_card(
            key="valuation_rate_gap",
            label="估值利率差",
            value=valuation_gap,
            status="proxy" if valuation_gap is not None else "missing",
            detail=valuation_detail,
            source=panel_source,
        ),
        _metric_card(
            key="theme_valuation",
            label="主题估值因子",
            value=theme_valuation,
            status="available" if theme_valuation is not None else "missing",
            detail="来自日报主题评分，不等价于指数 NTM PE。",
            source="out/scores.json / FMP / SEC EDGAR",
            ref_ids=("fmp", "sec-edgar"),
        ),
    ]


def _drawdown_levels(high: float | None) -> list[dict[str, object]]:
    if high is None:
        return []
    levels: list[dict[str, object]] = []
    for drawdown in (0, -5, -10, -15, -20, -30):
        levels.append(
            {
                "drawdownPct": float(drawdown),
                "price": round(high * (1 + drawdown / 100), 2),
            }
        )
    return levels


def _terminal_drawdown_rows(
    cross_market: Mapping[str, Any], panel: PanelDocument
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    latest_row = _latest_panel_row(panel.rows)
    specs = (
        (
            "SPY",
            "S&P 500 ETF",
            ("spy_high", "spy_52w_high", "spx_high"),
            ("spx_ntm_pe", "spy_ntm_pe"),
        ),
        (
            "QQQ",
            "NASDAQ-100 ETF",
            ("qqq_high", "qqq_52w_high", "ndx_high"),
            ("ndx_ntm_pe", "qqq_ntm_pe"),
        ),
    )
    for ticker, label, high_columns, pe_columns in specs:
        close = _stock_value(cross_market, ticker)
        pct_chg = _stock_pct_change(cross_market, ticker)
        high = _rounded(_first_present(*(latest_row.get(column) for column in high_columns)))
        ntm_pe = _rounded(_first_present(*(latest_row.get(column) for column in pe_columns)))
        current_drawdown = (
            round((close / high - 1) * 100, 2)
            if close is not None and high is not None and high != 0
            else None
        )
        rows.append(
            {
                "ticker": ticker,
                "label": label,
                "close": close,
                "pctChg": pct_chg,
                "high": high,
                "currentDrawdown": current_drawdown,
                "ntmPe": ntm_pe,
                "levels": _drawdown_levels(high),
                "status": "proxy" if close is not None else "missing",
                "detail": (
                    "已接入当前价格；历史高点和 PE 只在状态面板提供时计算。"
                    if close is not None
                    else "缺少 SPY/QQQ 当前价格。"
                ),
            }
        )
    return rows


def _event_source_chain(entry: Mapping[str, Any]) -> list[dict[str, str]]:
    chain: list[dict[str, str]] = []
    raw_chain = entry.get("sourceChain") or entry.get("source_chain")
    for raw_item in _as_list(raw_chain):
        item = _as_mapping(raw_item)
        source = str(item.get("source") or item.get("name") or "")
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")
        if source or url:
            chain.append({"source": source, "url": url, "title": title})
    if not chain and (entry.get("source") or entry.get("url")):
        chain.append(
            {
                "source": str(entry.get("source") or ""),
                "url": str(entry.get("url") or ""),
                "title": str(entry.get("title") or ""),
            }
        )
    return chain


def _terminal_event_items(
    scores: Mapping[str, Any], raw_events: Mapping[str, Any], limit: int = 8
) -> list[dict[str, object]]:
    candidate = raw_events.get("ai_updates")
    if not isinstance(candidate, list):
        candidate = scores.get("ai_updates")
    items: list[dict[str, object]] = []
    for item in _as_list(candidate)[:limit]:
        entry = _as_mapping(item)
        title = str(entry.get("title") or entry.get("market") or "市场更新")
        items.append(
            {
                "title": title,
                "date": str(entry.get("prompt_date") or entry.get("date") or ""),
                "source": str(entry.get("source") or entry.get("provider") or ""),
                "url": str(entry.get("url") or ""),
                "sourceChain": _event_source_chain(entry),
            }
        )
    return items


def _module_status(*, key: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _terminal_payload(
    *,
    scores: Mapping[str, Any],
    cross_market: Mapping[str, Any],
    raw_events: Mapping[str, Any],
    latest: Mapping[str, Any],
    panel: PanelDocument,
    neighbors: Sequence[Mapping[str, object]],
    neighbor_summary: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    sentiment_cards = _terminal_sentiment_cards(latest, cross_market, panel)
    valuation_cards = _terminal_valuation_cards(scores, latest, panel)
    drawdown_rows = _terminal_drawdown_rows(cross_market, panel)
    event_items = _terminal_event_items(scores, raw_events)
    sentiment_status = (
        "proxy"
        if any(item["status"] in {"available", "proxy"} for item in sentiment_cards)
        else "missing"
    )
    valuation_status = (
        "proxy"
        if any(item["status"] in {"available", "proxy"} for item in valuation_cards)
        else "missing"
    )
    drawdown_status = (
        "proxy"
        if any(item["status"] in {"available", "proxy"} for item in drawdown_rows)
        else "missing"
    )
    return {
        "sentimentCards": sentiment_cards,
        "valuationCards": valuation_cards,
        "drawdownRows": drawdown_rows,
        "eventItems": event_items,
        "modules": [
            _module_status(
                key="market-sentiment",
                label="市场情绪",
                status=sentiment_status,
                detail="VIX 已接入；Fear & Greed、宽度和波动率结构按本地可用性展示。",
            ),
            _module_status(
                key="valuation",
                label="核心估值",
                status=valuation_status,
                detail="NTM PE/EPS 数据缺失时只展示估值代理和主题估值因子。",
            ),
            _module_status(
                key="drawdown-levels",
                label="回撤点位",
                status=drawdown_status,
                detail="当前价格可用；历史高点、隐含 PE 和分位依赖可选状态面板。",
            ),
            _module_status(
                key="regime-backtest",
                label="状态回测",
                status="proxy" if neighbors and neighbor_summary else "missing",
                detail="使用本地代理特征寻找相似历史状态，尚非目标站原始特征。",
            ),
            _module_status(
                key="strategy-lab",
                label="策略实验室",
                status="missing",
                detail="未接入自然语言策略解析、规则编译和回测沙箱。",
            ),
            _module_status(
                key="event-feed",
                label="事件流",
                status="available" if event_items else "missing",
                detail="可从 raw_events 或 scores 的 AI 更新生成只读事件列表和来源链。",
            ),
        ],
    }
