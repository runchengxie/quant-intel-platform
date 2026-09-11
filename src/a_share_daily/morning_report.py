"""确定性的晨报渲染器。

报告由结构化事实拼装。LLM/search 只提供候选新闻，本渲染器只消费
带来源和 URL 的已校验 ``items``。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from a_share_daily.freshness import render_freshness_section
from a_share_daily.global_leadlag import GLOBAL_LEAD_LAG_INSTRUMENTS, INDEX_LABELS
from a_share_daily.report_theme import get_report_theme

NEWS_MARKET_ORDER = ("cn", "jp", "kr", "us")
NEWS_MARKET_LABELS = {"cn": "A股", "jp": "日股", "kr": "韩股", "us": "美股"}
CATEGORY_LABELS = {
    "policy": "政策",
    "company": "公司",
    "macro": "宏观",
    "sector": "行业",
}


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_report(path: str | Path, text: str) -> Path:
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding="utf-8")
    return resolved


def _fmt_pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:+.2f}%"


def _fmt_close(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    return f"{number:.2f}"


def _days_since(as_of_date: Any, generated: datetime) -> int | None:
    if not isinstance(as_of_date, str) or not as_of_date:
        return None
    try:
        parsed = datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (generated.date() - parsed).days


def _quote_line(symbol: str, quotes: Mapping[str, Any], label: str | None = None) -> str | None:
    raw = quotes.get(symbol)
    if not isinstance(raw, Mapping) or "pct_chg" not in raw:
        return None
    name = label or INDEX_LABELS.get(symbol, symbol)
    return f"{name} {symbol} {_fmt_pct(raw.get('pct_chg'))}，收 {_fmt_close(raw.get('close'))}"


def _top_movers(
    quotes: Mapping[str, Any],
    symbols: Sequence[str],
    *,
    reverse: bool,
    limit: int = 3,
) -> list[str]:
    rows: list[tuple[float, str]] = []
    for symbol in symbols:
        raw = quotes.get(symbol)
        if not isinstance(raw, Mapping):
            continue
        value = raw.get("pct_chg")
        if not isinstance(value, (int, float, str)):
            continue
        try:
            pct = float(value)
        except (TypeError, ValueError):
            continue
        rows.append((pct, symbol))
    rows.sort(key=lambda item: item[0], reverse=reverse)
    return [f"{symbol} {pct:+.2f}%" for pct, symbol in rows[:limit]]


def _news_items(news: Mapping[str, Any], market: str, limit: int = 2) -> list[Mapping[str, Any]]:
    markets = news.get("markets")
    if not isinstance(markets, Mapping):
        return []
    entry = markets.get(market)
    if not isinstance(entry, Mapping):
        return []
    raw_items = entry.get("items")
    if not isinstance(raw_items, list):
        return []

    items: list[Mapping[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        if all(
            isinstance(item.get(field), str) and item.get(field)
            for field in ("summary", "source", "url")
        ):
            items.append(item)
        if len(items) >= limit:
            break
    return items


def _render_news_section(news: Mapping[str, Any]) -> list[str]:
    lines = ["## 1. 隔夜要闻"]
    added = 0
    for market in NEWS_MARKET_ORDER:
        label = NEWS_MARKET_LABELS.get(market, market.upper())
        for item in _news_items(news, market):
            category = CATEGORY_LABELS.get(str(item.get("category", "")), "新闻")
            summary = str(item.get("summary", "")).strip()
            source = str(item.get("source", "")).strip()
            title = str(item.get("title") or summary).strip()
            url = str(item.get("url", "")).strip()
            published_at = str(item.get("published_at", "")).strip()
            date_part = f"{published_at}，" if published_at else ""
            lines.append(
                f"- [fetch] {label}｜{category}: {summary}（{date_part}{source}: [{title}]({url})）"
            )
            added += 1
    if added == 0:
        lines.append("- [WARN] 未取得通过结构化校验的新闻条目；跳过自由文本新闻。")
    return lines


def _render_us_section(cross: Mapping[str, Any]) -> list[str]:
    quotes = cross.get("us_stocks") if isinstance(cross.get("us_stocks"), Mapping) else {}
    assert isinstance(quotes, Mapping)
    lines = ["## 2. 美股隔夜回顾"]
    benchmark_parts = [
        line for symbol in ("SPY", "QQQ", "SMH") if (line := _quote_line(symbol, quotes))
    ]
    if benchmark_parts:
        lines.append("- [fetch] " + "；".join(benchmark_parts))
    else:
        lines.append("- [WARN] 缺少 SPY/QQQ/SMH 基准行情。")

    core_symbols = ["NVDA", "AMD", "AVGO", "TSLA", "AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    winners = _top_movers(quotes, core_symbols, reverse=True)
    losers = _top_movers(quotes, core_symbols, reverse=False)
    if winners:
        lines.append("- 领涨: " + "，".join(winners))
    if losers:
        lines.append("- 领跌: " + "，".join(losers))

    smh = quotes.get("SMH") if isinstance(quotes.get("SMH"), Mapping) else {}
    qqq = quotes.get("QQQ") if isinstance(quotes.get("QQQ"), Mapping) else {}
    if isinstance(smh, Mapping) and isinstance(qqq, Mapping):
        try:
            spread = float(smh.get("pct_chg", 0)) - float(qqq.get("pct_chg", 0))
        except (TypeError, ValueError):
            spread = 0.0
        if abs(spread) >= 1:
            direction = "半导体相对强" if spread > 0 else "半导体相对弱"
            lines.append(f"- 关键矛盾: SMH 相对 QQQ {spread:+.2f}pp，{direction}。")
    return lines


def _render_asia_section(cross: Mapping[str, Any]) -> list[str]:
    quotes = cross.get("us_stocks") if isinstance(cross.get("us_stocks"), Mapping) else {}
    assert isinstance(quotes, Mapping)
    lines = ["## 3. 亚洲市场速览"]
    index_parts = [line for symbol in ("^N225", "^KS11") if (line := _quote_line(symbol, quotes))]
    if index_parts:
        lines.append("- [fetch] " + "；".join(index_parts))
    else:
        lines.append("- [WARN] 缺少日经/KOSPI 指数快照。")

    jp_symbols = [item.symbol for item in GLOBAL_LEAD_LAG_INSTRUMENTS if item.market == "JP"]
    kr_symbols = [item.symbol for item in GLOBAL_LEAD_LAG_INSTRUMENTS if item.market == "KR"]
    jp_movers = _top_movers(quotes, jp_symbols, reverse=True, limit=3)
    kr_movers = _top_movers(quotes, kr_symbols, reverse=True, limit=3)
    if jp_movers:
        lines.append("- 日本半导体: " + "，".join(jp_movers))
    if kr_movers:
        lines.append("- 韩国半导体: " + "，".join(kr_movers))
    return lines


def _render_mapping_section(cross: Mapping[str, Any]) -> list[str]:
    lines = ["## 4. 跨市场传导信号"]
    raw_mapping = cross.get("global_lead_lag") or cross.get("concept_mapping") or []
    mapping = (
        [item for item in raw_mapping if isinstance(item, Mapping)]
        if isinstance(raw_mapping, list)
        else []
    )
    significant = [item for item in mapping if abs(float(item.get("avg_pct_chg", 0) or 0)) >= 1]
    if not significant:
        lines.append("- [fetch] 全球领先资产映射波动均低于 1%，无显著传导。")
    else:
        for item in significant[:6]:
            signal = str(item.get("signal", "neutral"))
            tag = "[OK]" if signal == "bullish" else "[WARN]" if signal == "bearish" else "[fetch]"
            drivers = "，".join(str(driver) for driver in item.get("drivers", [])[:3])
            markets = "/".join(str(market) for market in item.get("markets", []))
            suffix = f"，市场 {markets}" if markets else ""
            lines.append(
                f"- {tag} {item.get('concept')}: {_fmt_pct(item.get('avg_pct_chg'))}{suffix}，驱动 {drivers or 'n/a'}"
            )

    raw_commodities = cross.get("commodity_concept_mapping") or []
    commodities = (
        [item for item in raw_commodities if isinstance(item, Mapping)]
        if isinstance(raw_commodities, list)
        else []
    )
    for item in commodities[:3]:
        drivers = "，".join(str(driver) for driver in item.get("drivers", [])[:2])
        lines.append(
            f"- [fetch] 商品映射 {item.get('concept')}: {_fmt_pct(item.get('avg_pct_chg'))}，{drivers}"
        )
    return lines


def _render_a_share_section(manifest: Mapping[str, Any], cross: Mapping[str, Any]) -> list[str]:
    lines = ["## 5. A股盘前热点预判"]
    topic_summary = (
        manifest.get("topic_summary") if isinstance(manifest.get("topic_summary"), Mapping) else {}
    )
    if topic_summary:
        topic_count = topic_summary.get("topic_count")
        skipped = bool(topic_summary.get("skipped"))
        if isinstance(topic_count, int) and topic_count > 0:
            lines.append(
                f"- [fetch] DailyWatch20 热点主题 {topic_count} 个，来源正式 topic_summary artifact。"
            )
        elif not skipped:
            reason = str(topic_summary.get("reason") or "topic_summary.json 不可用")
            lines.append(f"- [WARN] DailyWatch20 热点主题不可用（{reason}）。")
    if not topic_summary:
        hotsector = (
            manifest.get("hotsector") if isinstance(manifest.get("hotsector"), Mapping) else {}
        )
        candidates = hotsector.get("candidates") if isinstance(hotsector, Mapping) else None
        hotsector_skipped = (
            bool(hotsector.get("skipped")) if isinstance(hotsector, Mapping) else False
        )
        if isinstance(candidates, int) and candidates > 0:
            lines.append(
                f"- [fetch] 热点候选池 {candidates} 只，来源 research-workspace owner artifact。"
            )
        elif isinstance(hotsector, Mapping) and hotsector and not hotsector_skipped:
            reason = str(hotsector.get("reason") or "hotsector 产出 0 只候选")
            lines.append(f"- [WARN] 热点候选池为空（{reason}）。")
        else:
            lines.append("- [WARN] 未取得 hot-sector manifest。")

    raw_mapping = cross.get("global_lead_lag") or cross.get("concept_mapping") or []
    mapping = (
        [item for item in raw_mapping if isinstance(item, Mapping)]
        if isinstance(raw_mapping, list)
        else []
    )
    bullish = [item for item in mapping if str(item.get("signal")) == "bullish"][:5]
    bearish = [item for item in mapping if str(item.get("signal")) == "bearish"][-5:]
    if bullish:
        lines.append(
            "- 关注映射: "
            + "，".join(
                f"{item.get('concept')}({_fmt_pct(item.get('avg_pct_chg'))})" for item in bullish
            )
        )
    if bearish:
        lines.append(
            "- 风险映射: "
            + "，".join(
                f"{item.get('concept')}({_fmt_pct(item.get('avg_pct_chg'))})" for item in bearish
            )
        )
    return lines


def _render_macro_section(cross: Mapping[str, Any], generated: datetime) -> list[str]:
    lines = ["## 6. 宏观环境"]
    macros = cross.get("macros") if isinstance(cross.get("macros"), Mapping) else {}
    assert isinstance(macros, Mapping)
    freshness_warnings = cross.get("_freshness_warnings")
    if isinstance(freshness_warnings, list):
        for warning in freshness_warnings:
            lines.append(f"- [WARN] {warning}。")
    for symbol in ("^VIX", "DX-Y.NYB", "^TNX"):
        raw = macros.get(symbol)
        if not isinstance(raw, Mapping) or "close" not in raw:
            continue
        label = str(raw.get("label") or INDEX_LABELS.get(symbol, symbol))
        stale_days = raw.get("stale_days")
        if not isinstance(stale_days, int):
            stale_days = _days_since(raw.get("as_of_date"), generated)
        stale_part = (
            f"，滞后 {stale_days} 天" if isinstance(stale_days, int) and stale_days > 3 else ""
        )
        tag = "[WARN]" if stale_part else "[fetch]"
        as_of = f"，截至 {raw.get('as_of_date')}{stale_part}" if raw.get("as_of_date") else ""
        lines.append(
            f"- {tag} {label}: {_fmt_close(raw.get('close'))} ({_fmt_pct(raw.get('pct_chg'))}){as_of}"
        )

    aaii = cross.get("aaii_sentiment")
    if isinstance(aaii, Mapping) and "bull_bear_spread" in aaii:
        lines.append(
            "- [fetch] AAII: "
            f"看多 {aaii.get('bullish_pct', 'n/a')} / 看空 {aaii.get('bearish_pct', 'n/a')}，"
            f"多空差 {_fmt_pct(aaii.get('bull_bear_spread'))}"
        )
    if len(lines) == 1:
        lines.append("- [WARN] 宏观快照缺失。")
    return lines


def render_morning_report(
    manifest: Mapping[str, Any],
    news: Mapping[str, Any] | None = None,
    *,
    generated_at: datetime | None = None,
    theme: str = "research_editorial",
) -> str:
    generated = generated_at or datetime.now()
    date_text = str(
        manifest.get("date_dash") or manifest.get("date") or generated.strftime("%Y-%m-%d")
    )
    cross = (
        manifest.get("cross_market") if isinstance(manifest.get("cross_market"), Mapping) else {}
    )
    assert isinstance(cross, Mapping)
    news = news or {}
    selected_theme = get_report_theme(theme)
    freshness_title = "7. 数据质量"

    sections: list[list[str]] = [
        [
            f"# 亚洲市场盘前 / 美股市场盘后（{date_text}）",
            "",
            f"生成时间: {generated.strftime('%Y-%m-%d %H:%M')}",
            f"报告主题: {selected_theme.label}",
            "生成方式: market-intel 结构化事实 + 规则模板；未使用自由写作流程。",
        ],
        _render_news_section(news),
        _render_us_section(cross),
        _render_asia_section(cross),
        _render_mapping_section(cross),
        _render_a_share_section(manifest, cross),
        _render_macro_section(cross, generated),
    ]
    sections.append(render_freshness_section(manifest, news, title=freshness_title))

    lines: list[str] = []
    for section in sections:
        if lines:
            lines.append("")
        lines.extend(section)
    return "\n".join(lines).rstrip() + "\n"
