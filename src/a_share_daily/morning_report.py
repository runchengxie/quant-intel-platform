"""Render deterministic morning reports from validated structured facts and news."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from a_share_daily.freshness import render_freshness_section
from a_share_daily.global_leadlag import GLOBAL_LEAD_LAG_INSTRUMENTS, INDEX_LABELS
from a_share_daily.report_messages import CATEGORY_LABELS, NEWS_MARKET_LABELS, known_label, message
from a_share_daily.report_theme import get_report_theme
from ops_common.locale import normalize_locale

NEWS_MARKET_ORDER = ("cn", "jp", "kr", "us")


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


def _quote_line(
    symbol: str, quotes: Mapping[str, Any], label: str | None = None, locale: str = "zh-CN"
) -> str | None:
    raw = quotes.get(symbol)
    if not isinstance(raw, Mapping) or "pct_chg" not in raw:
        return None
    name = known_label(locale, label or INDEX_LABELS.get(symbol, symbol))
    return message(
        locale,
        "quote",
        name=f"{name}",
        symbol=f"{symbol}",
        change=f"{_fmt_pct(raw.get('pct_chg'))}",
        close=f"{_fmt_close(raw.get('close'))}",
    )


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


def _render_news_section(news: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    lines = [message(locale, "morning.news.title")]
    added = 0
    for market in NEWS_MARKET_ORDER:
        label = known_label(locale, NEWS_MARKET_LABELS.get(market, market.upper()))
        for item in _news_items(news, market):
            category = known_label(
                locale,
                CATEGORY_LABELS.get(
                    str(item.get("category", "")), message(locale, "news.category")
                ),
            )
            summary = str(item.get("summary", "")).strip()
            source = str(item.get("source", "")).strip()
            title = str(item.get("title") or summary).strip()
            url = str(item.get("url", "")).strip()
            published_at = str(item.get("published_at", "")).strip()
            date_part = published_at + message(locale, "separator.list") if published_at else ""
            lines.append(
                message(
                    locale,
                    "news.item",
                    market=label,
                    category=category,
                    summary=summary,
                    date=date_part,
                    source=source,
                    title=title,
                    url=url,
                )
            )
            added += 1
    if added == 0:
        lines.append(message(locale, "morning.news.missing"))
    return lines


def _render_us_section(cross: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    quotes = cross.get("us_stocks") if isinstance(cross.get("us_stocks"), Mapping) else {}
    assert isinstance(quotes, Mapping)
    lines = [message(locale, "morning.us.title")]
    benchmark_parts = [
        line
        for symbol in ("SPY", "QQQ", "SMH")
        if (line := _quote_line(symbol, quotes, locale=locale))
    ]
    if benchmark_parts:
        lines.append("- [fetch] " + message(locale, "separator.clause").join(benchmark_parts))
    else:
        lines.append(message(locale, "morning.us.missing"))

    core_symbols = ["NVDA", "AMD", "AVGO", "TSLA", "AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    winners = _top_movers(quotes, core_symbols, reverse=True)
    losers = _top_movers(quotes, core_symbols, reverse=False)
    if winners:
        lines.append(message(locale, "leaders") + message(locale, "separator.list").join(winners))
    if losers:
        lines.append(message(locale, "laggards") + message(locale, "separator.list").join(losers))

    smh = quotes.get("SMH") if isinstance(quotes.get("SMH"), Mapping) else {}
    qqq = quotes.get("QQQ") if isinstance(quotes.get("QQQ"), Mapping) else {}
    if isinstance(smh, Mapping) and isinstance(qqq, Mapping):
        try:
            spread = float(smh.get("pct_chg", 0)) - float(qqq.get("pct_chg", 0))
        except (TypeError, ValueError):
            spread = 0.0
        if abs(spread) >= 1:
            direction = (
                message(locale, "semiconductor.strong")
                if spread > 0
                else message(locale, "semiconductor.weak")
            )
            lines.append(
                message(
                    locale, "morning.us.spread", spread=f"{spread:+.2f}", direction=f"{direction}"
                )
            )
    return lines


def _render_asia_section(cross: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    quotes = cross.get("us_stocks") if isinstance(cross.get("us_stocks"), Mapping) else {}
    assert isinstance(quotes, Mapping)
    lines = [message(locale, "morning.asia.title")]
    index_parts = [
        line
        for symbol in ("^N225", "^KS11")
        if (line := _quote_line(symbol, quotes, locale=locale))
    ]
    if index_parts:
        lines.append("- [fetch] " + message(locale, "separator.clause").join(index_parts))
    else:
        lines.append(message(locale, "morning.asia.missing"))

    jp_symbols = [item.symbol for item in GLOBAL_LEAD_LAG_INSTRUMENTS if item.market == "JP"]
    kr_symbols = [item.symbol for item in GLOBAL_LEAD_LAG_INSTRUMENTS if item.market == "KR"]
    jp_movers = _top_movers(quotes, jp_symbols, reverse=True, limit=3)
    kr_movers = _top_movers(quotes, kr_symbols, reverse=True, limit=3)
    if jp_movers:
        lines.append(
            message(locale, "japan.semiconductors")
            + message(locale, "separator.list").join(jp_movers)
        )
    if kr_movers:
        lines.append(
            message(locale, "korea.semiconductors")
            + message(locale, "separator.list").join(kr_movers)
        )

    lines.extend(_render_korea_signals(cross, locale))
    return lines


def _render_korea_signals(cross: Mapping[str, Any], locale: str) -> list[str]:
    """Format the optional Korean-session signals without changing their facts."""
    lines: list[str] = []
    preopen = cross.get("korea_preopen")
    if isinstance(preopen, Mapping) and preopen.get("source") != "unavailable":
        signal = str(preopen.get("signal", "neutral"))
        tag = "[OK]" if signal == "bullish" else "[WARN]" if signal == "bearish" else "[fetch]"
        concepts = message(locale, "separator.enumeration").join(
            str(item) for item in preopen.get("concepts", [])[:5]
        ) or message(locale, "korea.assets")
        source = (
            message(locale, "daily.proxy")
            if preopen.get("source") == "daily-proxy"
            else str(preopen.get("source", "unknown"))
        )
        residual = float(preopen.get("residual_pct_chg", 0) or 0)
        alert = preopen.get("risk_level") == "high" or abs(residual) >= 2
        if alert:
            lines.append(
                message(
                    locale,
                    "korea.preopen.alert",
                    tag=f"{tag}",
                    signal=f"{signal}",
                    residual=f"{residual:+.1f}",
                    concepts=f"{concepts}",
                    source=f"{source}",
                )
            )
        else:
            lines.append(
                message(
                    locale,
                    "korea.preopen",
                    tag=f"{tag}",
                    signal=f"{signal}",
                    residual=f"{residual:+.1f}",
                    source=f"{source}",
                )
            )

    overnight = cross.get("korea_overnight")
    if isinstance(overnight, Mapping) and overnight.get("source") != "unavailable":
        signal = str(overnight.get("signal", "neutral"))
        tag = "[WARN]" if signal == "bearish" else "[OK]" if signal == "bullish" else "[fetch]"
        level = str(overnight.get("risk_level", "unknown"))
        drivers = message(locale, "separator.list").join(
            str(item) for item in overnight.get("drivers", [])[:3]
        ) or message(locale, "unavailable")
        source = (
            message(locale, "daily.proxy")
            if overnight.get("source") == "daily-proxy"
            else str(overnight.get("source", "unknown"))
        )
        alert = level == "high"
        if alert:
            lines.append(
                message(
                    locale,
                    "korea.overnight.alert",
                    tag=f"{tag}",
                    level=f"{level}",
                    signal=f"{signal}",
                    drivers=f"{drivers}",
                    source=f"{source}",
                )
            )
        else:
            lines.append(
                message(
                    locale,
                    "korea.overnight",
                    tag=f"{tag}",
                    level=f"{level}",
                    signal=f"{signal}",
                    source=f"{source}",
                )
            )
    return lines


def _render_mapping_section(cross: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    lines = [message(locale, "morning.mapping.title")]
    raw_mapping = cross.get("global_lead_lag") or cross.get("concept_mapping") or []
    mapping = (
        [item for item in raw_mapping if isinstance(item, Mapping)]
        if isinstance(raw_mapping, list)
        else []
    )
    significant = [item for item in mapping if abs(float(item.get("avg_pct_chg", 0) or 0)) >= 1]
    if not significant:
        lines.append(message(locale, "morning.mapping.missing"))
    else:
        for item in significant[:6]:
            signal = str(item.get("signal", "neutral"))
            tag = "[OK]" if signal == "bullish" else "[WARN]" if signal == "bearish" else "[fetch]"
            drivers = message(locale, "separator.list").join(
                str(driver) for driver in item.get("drivers", [])[:3]
            )
            markets = "/".join(str(market) for market in item.get("markets", []))
            suffix = message(locale, "mapping.markets", markets=f"{markets}") if markets else ""
            lines.append(
                message(
                    locale,
                    "morning.mapping.row",
                    tag=f"{tag}",
                    concept=f"{item.get('concept')}",
                    change=f"{_fmt_pct(item.get('avg_pct_chg'))}",
                    suffix=f"{suffix}",
                    drivers=f"{drivers or 'n/a'}",
                )
            )

    raw_commodities = cross.get("commodity_concept_mapping") or []
    commodities = (
        [item for item in raw_commodities if isinstance(item, Mapping)]
        if isinstance(raw_commodities, list)
        else []
    )
    for item in commodities[:3]:
        drivers = message(locale, "separator.list").join(
            str(driver) for driver in item.get("drivers", [])[:2]
        )
        lines.append(
            message(
                locale,
                "morning.commodity.row",
                concept=f"{item.get('concept')}",
                change=f"{_fmt_pct(item.get('avg_pct_chg'))}",
                drivers=f"{drivers}",
            )
        )
    return lines


def _render_a_share_section(
    manifest: Mapping[str, Any], cross: Mapping[str, Any], locale: str = "zh-CN"
) -> list[str]:
    lines = [message(locale, "morning.ashare.title")]
    topic_summary = (
        manifest.get("topic_summary") if isinstance(manifest.get("topic_summary"), Mapping) else {}
    )
    if topic_summary:
        topic_count = topic_summary.get("topic_count")
        skipped = bool(topic_summary.get("skipped"))
        if isinstance(topic_count, int) and topic_count > 0:
            lines.append(message(locale, "morning.topics", count=f"{topic_count}"))
        elif not skipped:
            reason = str(topic_summary.get("reason") or message(locale, "topics.unavailable"))
            lines.append(message(locale, "morning.topics.missing", reason=f"{reason}"))
    if not topic_summary:
        hotsector = (
            manifest.get("hotsector") if isinstance(manifest.get("hotsector"), Mapping) else {}
        )
        candidates = hotsector.get("candidates") if isinstance(hotsector, Mapping) else None
        hotsector_skipped = (
            bool(hotsector.get("skipped")) if isinstance(hotsector, Mapping) else False
        )
        if isinstance(candidates, int) and candidates > 0:
            lines.append(message(locale, "morning.candidates", count=f"{candidates}"))
        elif isinstance(hotsector, Mapping) and hotsector and not hotsector_skipped:
            reason = str(hotsector.get("reason") or message(locale, "candidates.empty"))
            lines.append(message(locale, "morning.candidates.empty", reason=f"{reason}"))
        else:
            lines.append(message(locale, "morning.manifest.missing"))

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
            message(locale, "mapping.watch")
            + message(locale, "separator.list").join(
                f"{item.get('concept')}({_fmt_pct(item.get('avg_pct_chg'))})" for item in bullish
            )
        )
    if bearish:
        lines.append(
            message(locale, "mapping.risk")
            + message(locale, "separator.list").join(
                f"{item.get('concept')}({_fmt_pct(item.get('avg_pct_chg'))})" for item in bearish
            )
        )
    return lines


def _render_macro_section(
    cross: Mapping[str, Any], generated: datetime, locale: str = "zh-CN"
) -> list[str]:
    lines = [message(locale, "morning.macro.title")]
    macros = cross.get("macros") if isinstance(cross.get("macros"), Mapping) else {}
    assert isinstance(macros, Mapping)
    freshness_warnings = cross.get("_freshness_warnings")
    if isinstance(freshness_warnings, list):
        for warning in freshness_warnings:
            lines.append(message(locale, "warning.source", warning=warning))
    for symbol in ("^VIX", "DX-Y.NYB", "^TNX"):
        raw = macros.get(symbol)
        if not isinstance(raw, Mapping) or "close" not in raw:
            continue
        label = known_label(locale, raw.get("label") or INDEX_LABELS.get(symbol, symbol))
        stale_days = raw.get("stale_days")
        if not isinstance(stale_days, int):
            stale_days = _days_since(raw.get("as_of_date"), generated)
        stale_part = (
            message(locale, "lag.days", days=f"{stale_days}")
            if isinstance(stale_days, int) and stale_days > 3
            else ""
        )
        tag = "[WARN]" if stale_part else "[fetch]"
        as_of = (
            message(locale, "asof", date=f"{raw.get('as_of_date')}", lag=f"{stale_part}")
            if raw.get("as_of_date")
            else ""
        )
        lines.append(
            f"- {tag} {label}: {_fmt_close(raw.get('close'))} ({_fmt_pct(raw.get('pct_chg'))}){as_of}"
        )

    aaii = cross.get("aaii_sentiment")
    if isinstance(aaii, Mapping) and "bull_bear_spread" in aaii:
        lines.append(
            message(
                locale,
                "morning.aaii",
                bullish=f"{aaii.get('bullish_pct', 'n/a')}",
                bearish=f"{aaii.get('bearish_pct', 'n/a')}",
                spread=f"{_fmt_pct(aaii.get('bull_bear_spread'))}",
            )
        )
    if len(lines) == 1:
        lines.append(message(locale, "morning.macro.missing"))
    return lines


def render_morning_report(
    manifest: Mapping[str, Any],
    news: Mapping[str, Any] | None = None,
    *,
    generated_at: datetime | None = None,
    theme: str = "research_editorial",
    locale: str = "en-US",
) -> str:
    selected_locale = normalize_locale(locale)
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
    freshness_title = message(selected_locale, "freshness.title")
    title = message(selected_locale, "morning.title", date=date_text)
    generated_label = message(selected_locale, "report.generated")
    theme_label = message(selected_locale, "report.theme")
    method_label = message(selected_locale, "report.method.label")
    method_text = message(selected_locale, "report.method")

    sections: list[list[str]] = [
        [
            title,
            "",
            f"{generated_label}: {generated.strftime('%Y-%m-%d %H:%M')}",
            f"{theme_label}: {known_label(selected_locale, selected_theme.label)}",
            f"{method_label}: {method_text}",
        ],
        _render_news_section(news, locale=selected_locale),
        _render_us_section(cross, locale=selected_locale),
        _render_asia_section(cross, locale=selected_locale),
        _render_mapping_section(cross, locale=selected_locale),
        _render_a_share_section(manifest, cross, locale=selected_locale),
        _render_macro_section(cross, generated, locale=selected_locale),
    ]
    sections.append(
        render_freshness_section(manifest, news, title=freshness_title, locale=selected_locale)
    )

    if selected_locale == "en-US":
        sections[0].append(message(selected_locale, "report.source_language"))

    lines: list[str] = []
    for section in sections:
        if lines:
            lines.append("")
        lines.extend(section)
    return "\n".join(lines).rstrip() + "\n"
