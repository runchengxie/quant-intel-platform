"""晚间播报的 markdown 渲染层。

接收结构化 payload（review/news/manifest），产出确定性 markdown 段落，
无副作用、不调用任何外部投递通道。纯格式化逻辑依赖 _format 子模块。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from a_share_daily.delivery._format import (
    _date_dash,
    _dict,
    _fmt_close,
    _fmt_pct,
    _fmt_yuan,
    _list,
)
from a_share_daily.freshness import render_freshness_section

NEWS_MARKET_ORDER = ("cn", "jp", "kr", "us")
NEWS_MARKET_LABELS = {"cn": "A股", "jp": "日股", "kr": "韩股", "us": "美股"}
CATEGORY_LABELS = {
    "policy": "政策",
    "company": "公司",
    "macro": "宏观",
    "sector": "行业",
}


def _news_items(news: Mapping[str, Any], market: str, limit: int = 2) -> list[Mapping[str, Any]]:
    markets = _dict(news.get("markets"))
    entry = _dict(markets.get(market))
    items: list[Mapping[str, Any]] = []
    for item in _list(entry.get("items")):
        if not isinstance(item, Mapping):
            continue
        if all(
            isinstance(item.get(field), str) and str(item.get(field)).strip()
            for field in ("summary", "source", "url", "published_at")
        ):
            items.append(item)
        if len(items) >= limit:
            break
    return items


def _news_error_lines(news: Mapping[str, Any], limit: int = 4) -> list[str]:
    if news.get("disabled") is True:
        return ["AI 新闻抓取已关闭。"]
    errors: list[str] = []
    top_error = str(news.get("error") or "").strip()
    if top_error:
        errors.append(top_error)
    markets = _dict(news.get("markets"))
    for market in NEWS_MARKET_ORDER:
        entry = _dict(markets.get(market))
        error = str(entry.get("error") or "").strip()
        if not error:
            attempts = [
                item
                for item in _list(entry.get("attempts"))
                if isinstance(item, Mapping) and item.get("error")
            ]
            if attempts:
                error = str(attempts[-1].get("error") or "").strip()
        if error:
            label = NEWS_MARKET_LABELS.get(market, market.upper())
            errors.append(f"{label}: {error}")
        if len(errors) >= limit:
            break
    seen: set[str] = set()
    result: list[str] = []
    for error in errors:
        if error in seen:
            continue
        seen.add(error)
        result.append(error)
    return result[:limit]


def _render_evening_news(news: Mapping[str, Any]) -> list[str]:
    lines = ["## 2. 今日要闻"]
    added = 0
    for market in NEWS_MARKET_ORDER:
        label = NEWS_MARKET_LABELS.get(market, market.upper())
        for item in _news_items(news, market, limit=2):
            category = CATEGORY_LABELS.get(str(item.get("category", "")), "新闻")
            summary = str(item.get("summary", "")).strip()
            source = str(item.get("source", "")).strip()
            title = str(item.get("title") or summary).strip()
            url = str(item.get("url", "")).strip()
            published_at = str(item.get("published_at", "")).strip()
            lines.append(
                f"- [fetch] {label}｜{category}: {summary}（{published_at}，{source}: [{title}]({url})）"
            )
            added += 1
    if added == 0:
        lines.append("- [WARN] 未取得含 source/url/published_at 的结构化新闻条目。")
        for error in _news_error_lines(news):
            lines.append(f"- [WARN] AI news: {error}")
    return lines


def _render_evening_asia(review: Mapping[str, Any]) -> list[str]:
    """Render the legacy Asian post-market fact summary."""
    lines = ["## 3. 亚洲市场盘后复盘"]
    indices = _dict(review.get("indices"))
    if indices:
        parts = []
        for info in indices.values():
            if not isinstance(info, Mapping):
                continue
            parts.append(
                f"{info.get('name', '指数')} {_fmt_pct(info.get('pct_chg'))}，收 {_fmt_close(info.get('close'))}"
            )
        if parts:
            lines.append("- [fetch] " + "；".join(parts[:5]))

    overview = _dict(review.get("overview"))
    breadth = _dict(overview.get("breadth"))
    if overview:
        turnover = _fmt_yuan(float(overview.get("turnover_total", 0) or 0) * 1000)
        lines.append(
            "- [fetch] "
            f"A股中位数 {_fmt_pct(overview.get('median_pct_chg'))}，"
            f"加权 {_fmt_pct(overview.get('wavg_pct_chg'))}，"
            f"成交 {turnover}，上涨率 {breadth.get('up_ratio', 'n/a')}%。"
        )
        lines.append(
            "- [fetch] "
            f"上涨 {breadth.get('up', 'n/a')} 家，下跌 {breadth.get('down', 'n/a')} 家，"
            f"站上 VWAP 比例 {overview.get('vwap_above_ratio', 'n/a')}%。"
        )

    limits = _dict(review.get("limits"))
    limit_up = _dict(limits.get("limit_up"))
    limit_down = _dict(limits.get("limit_down"))
    down_limit_method = str(limit_down.get("method", "")).strip()
    down_limit_is_exact = down_limit_method == "exchange_limit_price"
    down_limit_count = limit_down.get("count")
    if down_limit_count is None:
        down_limit_count = overview.get(
            "down_limit_count" if down_limit_is_exact else "down_limit_approx", 0
        )
    down_limit_label = "跌停" if down_limit_is_exact else "跌停（近似）"
    limit_up_count = limit_up.get("count")
    limit_up_display = limit_up_count if limit_up_count is not None else "n/a"
    lines.append(
        "- [fetch] "
        f"涨停 {limit_up_display} 家，"
        f"{down_limit_label} {down_limit_count} 家，"
        f"最高连板 {limits.get('max_board', 0)} 板。"
    )

    moneyflow = _dict(review.get("moneyflow"))
    northbound = _dict(moneyflow.get("northbound"))
    if northbound:
        lines.append(f"- [fetch] 北向净流入 {_fmt_yuan(northbound.get('north_net'))}。")

    sectors = _dict(review.get("hot_sectors"))
    top_sectors = [
        item for item in _list(sectors.get("top_by_change")) if isinstance(item, Mapping)
    ]
    if top_sectors:
        rendered = "，".join(
            f"{item.get('name')}({_fmt_pct(item.get('pct_change'))})" for item in top_sectors[:5]
        )
        lines.append(f"- [fetch] 热门概念: {rendered}。")
    return lines


_MARKET_TEMPERATURE_DIMENSIONS = (
    ("liquidity", "流动性"),
    ("breadth", "广度"),
    ("profit_effect", "赚钱效应"),
    ("loss_risk", "亏钱风险"),
    ("trend_confirmation", "趋势确认"),
    ("rotation_quality", "轮动质量"),
)


def _fmt_score(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:.1f}" if math.isfinite(number) else "n/a"


def _render_evening_market_temperature(review: Mapping[str, Any]) -> list[str]:
    temperature = _dict(review.get("market_temperature"))
    if not temperature:
        return [
            "## 1. 市场温度",
            "- [WARN] 市场温度数据不足；第 3 节仍保留原始市场事实。",
        ]

    lines = ["## 1. 市场温度"]
    status = str(temperature.get("status_label") or "数据不足").strip()
    lines.append(
        "- [fetch] "
        f"状态: {status}；热度 {_fmt_score(temperature.get('heat_score'))}/100，"
        f"脆弱度 {_fmt_score(temperature.get('fragility_score'))}/100。"
    )

    dimensions = _dict(temperature.get("dimensions"))
    rendered_dimensions: list[str] = []
    for key, fallback_label in _MARKET_TEMPERATURE_DIMENSIONS:
        dimension = _dict(dimensions.get(key))
        label = str(dimension.get("label") or fallback_label).strip()
        rendered_dimensions.append(f"{label} {_fmt_score(dimension.get('score'))}")
    lines.append("- [fetch] 六维: " + "｜".join(rendered_dimensions) + "。")

    tensions = [
        str(item.get("summary", "")).strip()
        for item in _list(temperature.get("core_tensions"))
        if isinstance(item, Mapping) and str(item.get("summary", "")).strip()
    ]
    if tensions:
        lines.append("- [WARN] 核心矛盾: " + "；".join(tensions[:2]) + "。")
    lines.append("- [fetch] 口径: 仅作市场状态观察，当前刻度不直接映射仓位。")
    return lines


def _quote_line(symbol: str, quotes: Mapping[str, Any], label: str | None = None) -> str | None:
    raw = _dict(quotes.get(symbol))
    if not raw:
        return None
    name = label or symbol
    return f"{name} {symbol} {_fmt_pct(raw.get('pct_chg'))}，收 {_fmt_close(raw.get('close'))}"


def _render_evening_us_preview(manifest: Mapping[str, Any]) -> list[str]:
    lines = ["## 4. 美股盘前预览"]
    cross = _dict(manifest.get("cross_market"))
    quotes = _dict(cross.get("us_stocks"))
    parts = []
    for symbol, label in (("SPY", "标普500 ETF"), ("QQQ", "纳指100 ETF"), ("SMH", "半导体 ETF")):
        line = _quote_line(symbol, quotes, label)
        if line:
            parts.append(line)
    if parts:
        lines.append("- [fetch] 最新可用美股/ETF快照: " + "；".join(parts))
    else:
        lines.append("- [WARN] 缺少 SPY/QQQ/SMH 最新可用快照，盘前预览降级。")

    core = []
    for symbol in ("NVDA", "AMD", "AVGO", "TSLA", "AAPL", "MSFT", "META"):
        raw = _dict(quotes.get(symbol))
        if raw and "pct_chg" in raw:
            core.append((float(raw.get("pct_chg", 0) or 0), symbol))
    if core:
        core.sort(reverse=True)
        lines.append(
            "- [fetch] 核心股相对强弱: "
            + "，".join(f"{symbol} {pct:+.2f}%" for pct, symbol in core[:5])
            + "。"
        )
    return lines


def _render_evening_transmission(manifest: Mapping[str, Any]) -> list[str]:
    lines = ["## 5. 跨市场传导"]
    cross = _dict(manifest.get("cross_market"))
    mappings = _list(cross.get("global_lead_lag") or cross.get("concept_mapping"))
    significant = [
        item
        for item in mappings
        if isinstance(item, Mapping) and abs(float(item.get("avg_pct_chg", 0) or 0)) >= 1
    ]
    if not significant:
        lines.append("- [fetch] 全球领先资产映射波动低于 1% 或暂缺，未给出强传导信号。")
    else:
        for item in significant[:5]:
            signal = str(item.get("signal", "neutral"))
            tag = "[OK]" if signal == "bullish" else "[WARN]" if signal == "bearish" else "[fetch]"
            drivers = "，".join(str(driver) for driver in _list(item.get("drivers"))[:3])
            lines.append(
                f"- {tag} {item.get('concept')}: {_fmt_pct(item.get('avg_pct_chg'))}，驱动 {drivers or 'n/a'}。"
            )

    commodity_mappings = _list(cross.get("commodity_concept_mapping"))
    for item in commodity_mappings[:3]:
        if not isinstance(item, Mapping):
            continue
        drivers = "，".join(str(driver) for driver in _list(item.get("drivers"))[:2])
        lines.append(
            f"- [fetch] 商品映射 {item.get('concept')}: {_fmt_pct(item.get('avg_pct_chg'))}，{drivers or 'n/a'}。"
        )
    return lines


def _render_evening_macro(manifest: Mapping[str, Any]) -> list[str]:
    lines = ["## 6. 宏观环境"]
    cross = _dict(manifest.get("cross_market"))
    macros = _dict(cross.get("macros"))
    freshness_warnings = _list(cross.get("_freshness_warnings"))
    for warning in freshness_warnings:
        lines.append(f"- [WARN] {warning}。")
    for symbol in ("^VIX", "DX-Y.NYB", "^TNX"):
        raw = _dict(macros.get(symbol))
        if not raw:
            continue
        label = str(raw.get("label") or symbol)
        stale_days = raw.get("stale_days")
        stale_part = (
            f"，滞后 {stale_days} 天" if isinstance(stale_days, int) and stale_days > 3 else ""
        )
        tag = "[WARN]" if stale_part else "[fetch]"
        as_of = f"，截至 {raw.get('as_of_date')}{stale_part}" if raw.get("as_of_date") else ""
        lines.append(
            f"- {tag} {label}: {_fmt_close(raw.get('close'))} ({_fmt_pct(raw.get('pct_chg'))}){as_of}。"
        )
    aaii = _dict(cross.get("aaii_sentiment"))
    if aaii:
        lines.append(
            "- [fetch] AAII: "
            f"看多 {aaii.get('bullish_pct', 'n/a')} / 看空 {aaii.get('bearish_pct', 'n/a')}，"
            f"多空差 {_fmt_pct(aaii.get('bull_bear_spread'))}。"
        )
    if len(lines) == 1:
        lines.append("- [WARN] 宏观快照暂缺。")
    return lines


def _render_evening_next_watch(review: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]:
    lines = ["## 7. 次日验证"]
    temperature = _dict(review.get("market_temperature"))
    validation_descriptions = [
        str(item.get("description", "")).strip()
        for item in _list(temperature.get("validation_conditions"))
        if isinstance(item, Mapping) and str(item.get("description", "")).strip()
    ]
    if validation_descriptions:
        for description in validation_descriptions[:3]:
            punctuation = "" if description.endswith(("。", "！", "？")) else "。"
            lines.append(f"- [fetch] 次日验证: {description}{punctuation}")
    else:
        overview = _dict(review.get("overview"))
        median = float(overview.get("median_pct_chg", 0) or 0)
        direction = "风险偏好修复延续性" if median >= 0 else "弱势扩散是否收敛"
        lines.append(f"- [fetch] A股内部结构: 关注{direction}，以及成交额能否维持。")

    cross = _dict(manifest.get("cross_market"))
    quotes = _dict(cross.get("us_stocks"))
    smh = _dict(quotes.get("SMH"))
    qqq = _dict(quotes.get("QQQ"))
    if smh and qqq:
        try:
            spread = float(smh.get("pct_chg", 0) or 0) - float(qqq.get("pct_chg", 0) or 0)
        except (TypeError, ValueError):
            spread = 0.0
        tag = "[OK]" if spread >= 0 else "[WARN]"
        lines.append(f"- {tag} 美股半导体相对纳指差 {spread:+.2f}pp，影响次日科技成长映射。")
    lines.append("- [fetch] 次日开盘前复核: 美股收盘、美元/美债/VIX、日韩半导体链表现。")
    return lines


def build_evening_summary(
    trade_date: str,
    *,
    review_payload: Mapping[str, Any],
    news_payload: Mapping[str, Any],
    manifest_payload: Mapping[str, Any],
    generated_at: datetime | None = None,
) -> str:
    """Build the deterministic evening summary message."""
    generated = generated_at or datetime.now()
    freshness_title = "8. 数据质量"
    sections = [
        [
            f"# 美股市场盘前 / 亚洲市场盘后（{_date_dash(trade_date)}）",
            "",
            f"生成时间: {generated.strftime('%Y-%m-%d %H:%M')}",
            "生成方式: market-intel 结构化事实 + 规则模板；未使用自由写作流程。",
        ],
        _render_evening_market_temperature(review_payload),
        _render_evening_news(news_payload),
        _render_evening_asia(review_payload),
        _render_evening_us_preview(manifest_payload),
        _render_evening_transmission(manifest_payload),
        _render_evening_macro(manifest_payload),
        _render_evening_next_watch(review_payload, manifest_payload),
    ]
    sections.append(render_freshness_section(manifest_payload, news_payload, title=freshness_title))

    lines: list[str] = []
    for section in sections:
        if lines:
            lines.append("")
        lines.extend(section)
    return "\n".join(lines).rstrip() + "\n"
