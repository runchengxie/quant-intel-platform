"""Render deterministic evening Markdown without network or delivery side effects."""

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
from a_share_daily.report_messages import (
    _MARKET_TEMPERATURE_DIMENSIONS,
    CATEGORY_LABELS,
    NEWS_MARKET_LABELS,
    known_label,
    message,
)
from ops_common.locale import normalize_locale

NEWS_MARKET_ORDER = ("cn", "jp", "kr", "us")


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


def _news_error_lines(news: Mapping[str, Any], limit: int = 4, locale: str = "zh-CN") -> list[str]:
    if news.get("disabled") is True:
        return [message(locale, "news.disabled")]
    errors: list[str] = []
    top_error = str(news.get("error") or "").strip()
    if top_error:
        errors.append(top_error)
    markets = _dict(news.get("markets"))
    for market in NEWS_MARKET_ORDER:
        if market == "us":
            continue
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
            label = known_label(
                locale, NEWS_MARKET_LABELS.get(market, market.upper()), domain="market"
            )
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


def _render_evening_news(news: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    lines = [message(locale, "evening.news.title")]
    added = 0
    for market in NEWS_MARKET_ORDER:
        if market == "us":
            continue
        label = known_label(locale, NEWS_MARKET_LABELS.get(market, market.upper()), domain="market")
        for item in _news_items(news, market, limit=2):
            category = known_label(
                locale,
                CATEGORY_LABELS.get(
                    str(item.get("category", "")), message(locale, "news.category")
                ),
                domain="category",
            )
            summary = str(item.get("summary", "")).strip()
            source = str(item.get("source", "")).strip()
            title = str(item.get("title") or summary).strip()
            url = str(item.get("url", "")).strip()
            published_at = str(item.get("published_at", "")).strip()
            lines.append(
                message(
                    locale,
                    "news.item",
                    market=label,
                    category=category,
                    summary=summary,
                    date=published_at + message(locale, "separator.list"),
                    source=source,
                    title=title,
                    url=url,
                )
            )
            added += 1
    if added == 0:
        lines.append(message(locale, "evening.news.missing"))
        for error in _news_error_lines(news, locale=locale):
            lines.append(f"- [WARN] AI news: {error}")
    return lines


def _render_evening_asia(review: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    """Render the legacy Asian post-market fact summary."""
    lines = [message(locale, "evening.asia.title")]
    indices = _dict(review.get("indices"))
    if indices:
        parts = []
        for info in indices.values():
            if not isinstance(info, Mapping):
                continue
            parts.append(
                message(
                    locale,
                    "index.quote",
                    name=f"{info.get('name', message(locale, 'index'))}",
                    change=f"{_fmt_pct(info.get('pct_chg'))}",
                    close=f"{_fmt_close(info.get('close'))}",
                )
            )
        if parts:
            lines.append("- [fetch] " + message(locale, "separator.clause").join(parts[:5]))

    overview = _dict(review.get("overview"))
    breadth = _dict(overview.get("breadth"))
    if overview:
        turnover = _fmt_yuan(float(overview.get("turnover_total", 0) or 0) * 1000, locale=locale)
        lines.append(
            message(
                locale,
                "evening.overview",
                median=f"{_fmt_pct(overview.get('median_pct_chg'))}",
                weighted=f"{_fmt_pct(overview.get('wavg_pct_chg'))}",
                turnover=f"{turnover}",
                advancing=f"{breadth.get('up_ratio', 'n/a')}",
            )
        )
        lines.append(
            message(
                locale,
                "evening.breadth",
                up=f"{breadth.get('up', 'n/a')}",
                down=f"{breadth.get('down', 'n/a')}",
                above_vwap=f"{overview.get('vwap_above_ratio', 'n/a')}",
            )
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
    down_limit_label = (
        message(locale, "limit.down")
        if down_limit_is_exact
        else message(locale, "limit.down.approx")
    )
    limit_up_count = limit_up.get("count")
    limit_up_display = limit_up_count if limit_up_count is not None else "n/a"
    lines.append(
        message(
            locale,
            "evening.limits",
            up=f"{limit_up_display}",
            down_label=f"{down_limit_label}",
            down=f"{down_limit_count}",
            streak=f"{limits.get('max_board', 0)}",
        )
    )

    moneyflow = _dict(review.get("moneyflow"))
    northbound = _dict(moneyflow.get("northbound"))
    if northbound:
        lines.append(
            message(
                locale,
                "evening.northbound",
                amount=f"{_fmt_yuan(northbound.get('north_net'), locale=locale)}",
            )
        )

    sectors = _dict(review.get("hot_sectors"))
    top_sectors = [
        item for item in _list(sectors.get("top_by_change")) if isinstance(item, Mapping)
    ]
    if top_sectors:
        rendered = message(locale, "separator.list").join(
            f"{item.get('name')}({_fmt_pct(item.get('pct_change'))})" for item in top_sectors[:5]
        )
        lines.append(message(locale, "evening.sectors", sectors=f"{rendered}"))
    return lines


def _fmt_score(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:.1f}" if math.isfinite(number) else "n/a"


def _render_evening_market_temperature(
    review: Mapping[str, Any], locale: str = "zh-CN"
) -> list[str]:
    temperature = _dict(review.get("market_temperature"))
    if not temperature:
        return [
            message(locale, "evening.temperature.title"),
            message(locale, "evening.temperature.missing"),
        ]

    lines = [message(locale, "evening.temperature.title")]
    status = known_label(
        locale,
        temperature.get("status_label") or message(locale, "data.insufficient"),
        domain="temperature_status",
    ).strip()
    lines.append(
        message(
            locale,
            "evening.temperature",
            status=f"{status}",
            heat=f"{_fmt_score(temperature.get('heat_score'))}",
            fragility=f"{_fmt_score(temperature.get('fragility_score'))}",
        )
    )

    dimensions = _dict(temperature.get("dimensions"))
    rendered_dimensions: list[str] = []
    for key, fallback_label in _MARKET_TEMPERATURE_DIMENSIONS:
        dimension = _dict(dimensions.get(key))
        label = known_label(
            locale, dimension.get("label") or fallback_label, domain="dimension"
        ).strip()
        rendered_dimensions.append(f"{label} {_fmt_score(dimension.get('score'))}")
    lines.append(
        message(locale, "temperature.dimensions")
        + message(locale, "separator.dimensions").join(rendered_dimensions)
        + message(locale, "punctuation.stop")
    )

    tensions = [
        str(item.get("summary", "")).strip()
        for item in _list(temperature.get("core_tensions"))
        if isinstance(item, Mapping) and str(item.get("summary", "")).strip()
    ]
    if tensions:
        lines.append(
            message(locale, "temperature.tensions")
            + message(locale, "separator.clause").join(tensions[:2])
            + message(locale, "punctuation.stop")
        )
    lines.append(message(locale, "temperature.scope"))
    return lines


def _render_evening_transmission(manifest: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    lines = [message(locale, "evening.mapping.title")]
    cross = _dict(manifest.get("cross_market"))
    mappings = _list(cross.get("global_lead_lag") or cross.get("concept_mapping"))
    significant = [
        item
        for item in mappings
        if isinstance(item, Mapping) and abs(float(item.get("avg_pct_chg", 0) or 0)) >= 1
    ]
    if not significant:
        lines.append(message(locale, "evening.mapping.missing"))
    else:
        for item in significant[:5]:
            signal = str(item.get("signal", "neutral"))
            tag = "[OK]" if signal == "bullish" else "[WARN]" if signal == "bearish" else "[fetch]"
            drivers = message(locale, "separator.list").join(
                str(driver) for driver in _list(item.get("drivers"))[:3]
            )
            lines.append(
                message(
                    locale,
                    "evening.mapping.row",
                    tag=f"{tag}",
                    concept=f"{item.get('concept')}",
                    change=f"{_fmt_pct(item.get('avg_pct_chg'))}",
                    drivers=f"{drivers or 'n/a'}",
                )
            )

    commodity_mappings = _list(cross.get("commodity_concept_mapping"))
    for item in commodity_mappings[:3]:
        if not isinstance(item, Mapping):
            continue
        drivers = message(locale, "separator.list").join(
            str(driver) for driver in _list(item.get("drivers"))[:2]
        )
        lines.append(
            message(
                locale,
                "evening.commodity.row",
                concept=f"{item.get('concept')}",
                change=f"{_fmt_pct(item.get('avg_pct_chg'))}",
                drivers=f"{drivers or 'n/a'}",
            )
        )
    return lines


def _render_evening_macro(manifest: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    lines = [message(locale, "evening.macro.title")]
    cross = _dict(manifest.get("cross_market"))
    macros = _dict(cross.get("macros"))
    freshness_warnings = _list(cross.get("_freshness_warnings"))
    for warning in freshness_warnings:
        lines.append(message(locale, "warning.source", warning=warning))
    for symbol in ("^VIX", "DX-Y.NYB", "^TNX"):
        raw = _dict(macros.get(symbol))
        if not raw:
            continue
        label = known_label(locale, raw.get("label") or symbol, domain="macro")
        stale_days = raw.get("stale_days")
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
            message(
                locale,
                "macro.row",
                tag=tag,
                label=label,
                close=_fmt_close(raw.get("close")),
                change=_fmt_pct(raw.get("pct_chg")),
                asof=as_of,
            )
        )
    aaii = _dict(cross.get("aaii_sentiment"))
    if aaii:
        lines.append(
            message(
                locale,
                "evening.aaii",
                bullish=f"{aaii.get('bullish_pct', 'n/a')}",
                bearish=f"{aaii.get('bearish_pct', 'n/a')}",
                spread=f"{_fmt_pct(aaii.get('bull_bear_spread'))}",
            )
        )
    if len(lines) == 1:
        lines.append(message(locale, "evening.macro.missing"))
    return lines


def _render_evening_next_watch(review: Mapping[str, Any], locale: str = "zh-CN") -> list[str]:
    lines = [message(locale, "evening.watch.title")]
    temperature = _dict(review.get("market_temperature"))
    validation_descriptions = [
        str(item.get("description", "")).strip()
        for item in _list(temperature.get("validation_conditions"))
        if isinstance(item, Mapping) and str(item.get("description", "")).strip()
    ]
    if validation_descriptions:
        for description in validation_descriptions[:3]:
            punctuation = (
                ""
                if description.endswith((".", "!", "?", "。", "！", "？"))
                else message(locale, "punctuation.stop")
            )
            lines.append(
                message(
                    locale,
                    "evening.watch.row",
                    description=f"{description}",
                    punctuation=f"{punctuation}",
                )
            )
    else:
        overview = _dict(review.get("overview"))
        median = float(overview.get("median_pct_chg", 0) or 0)
        direction = (
            message(locale, "watch.recovery") if median >= 0 else message(locale, "watch.weakness")
        )
        lines.append(message(locale, "evening.watch.structure", direction=f"{direction}"))

    lines.append(message(locale, "evening.watch.global"))
    return lines


def build_evening_summary(  # noqa: PLR0913 - locale is an explicit presentation boundary
    trade_date: str,
    *,
    review_payload: Mapping[str, Any],
    news_payload: Mapping[str, Any],
    manifest_payload: Mapping[str, Any],
    generated_at: datetime | None = None,
    locale: str = "en-US",
) -> str:
    """Build the deterministic evening summary message."""
    selected_locale = normalize_locale(locale)
    generated = generated_at or datetime.now()
    freshness_title = message(selected_locale, "freshness.title")
    title = message(selected_locale, "evening.title", date=_date_dash(trade_date))
    generated_label = message(selected_locale, "report.generated")
    method_text = message(selected_locale, "report.method")

    sections = [
        [
            title,
            "",
            f"{generated_label}: {generated.strftime('%Y-%m-%d %H:%M')}",
            f"{message(selected_locale, 'report.method.label')}: {method_text}",
        ],
        _render_evening_market_temperature(review_payload, locale=selected_locale),
        _render_evening_news(news_payload, locale=selected_locale),
        _render_evening_asia(review_payload, locale=selected_locale),
        _render_evening_transmission(manifest_payload, locale=selected_locale),
        _render_evening_macro(manifest_payload, locale=selected_locale),
        _render_evening_next_watch(review_payload, locale=selected_locale),
    ]
    sections.append(
        render_freshness_section(
            manifest_payload, news_payload, title=freshness_title, locale=selected_locale
        )
    )

    if selected_locale == "en-US":
        sections[0].append(message(selected_locale, "report.source_language"))

    lines: list[str] = []
    for section in sections:
        if lines:
            lines.append("")
        lines.extend(section)
    return "\n".join(lines).rstrip() + "\n"
