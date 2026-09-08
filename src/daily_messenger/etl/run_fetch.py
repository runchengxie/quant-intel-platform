#!/usr/bin/env python3
"""Daily ETL entrypoint.

This script fetches (or simulates) the minimum viable data required for
subsequent scoring and report generation. It intentionally keeps the data
model small so it can be swapped with real data sources later.
"""

from __future__ import annotations

__all__ = [
    # re-export：供测试 monkeypatch / 外部通过 run_fetch.X 访问
    "aaii_sentiment",
    "ai_news",
    "cboe_putcall",
    "edgar",
    "fmp",
    "_safe_float",
    "_fetch_ai_market_news",
    "_fetch_gemini_market_news",
    "_fetch_ai_rss_events",
    "AI_NEWS_MARKET_SPECS",
    "_AiNewsSettings",
    "_resolve_ai_news_settings",
    "_extract_gemini_text",
    "_extract_glm_text",
    "_build_market_prompt",
    "_merge_sentiment_source",
    "_fetch_sentiment_payload",
]

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from daily_messenger.common import run_meta
from daily_messenger.common.logging import log, setup_logger
from daily_messenger.etl.config import (
    DEFAULT_AI_FEEDS,
    DEFAULT_ARXIV_PARAMS,
    DEFAULT_ARXIV_THROTTLE,
)
from daily_messenger.etl.config import (
    coerce_api_key as _coerce_api_key,
)
from daily_messenger.etl.config import (
    env_truthy as _env_truthy,
)
from daily_messenger.etl.config import (
    load_configuration as _load_configuration,
)

# aaii_sentiment / cboe_putcall 仅由测试通过 module.<attr> 打桩使用，run_fetch 自身不直接引用。
from daily_messenger.etl.fetchers import (
    aaii_sentiment,
    ai_news,
    cboe_putcall,
    edgar,
    fmp,
)
from daily_messenger.etl.fetchers._common import (
    _safe_float,
    _yahoo_allowed,
)
from daily_messenger.etl.fetchers.btc_flow import (
    _fetch_btc_payload,
)
from daily_messenger.etl.fetchers.events import (
    MAX_EVENT_ITEMS,
    _fetch_events_real,
    _fetch_finnhub_earnings,
)
from daily_messenger.etl.fetchers.hk import (
    _fetch_hk_market_snapshot,
)
from daily_messenger.etl.fetchers.normalize import (
    _normalize_raw_events_payload,
)
from daily_messenger.etl.fetchers.quotes import (
    _attempt_quote,
    _fetch_price_only_quotes,
    _fetch_quote_from_alpaca,
    _fetch_quote_from_alpha,
    _fetch_quote_from_fmp,
    _fetch_quote_from_stooq,
    _fetch_quote_from_twelve_data,
    _fetch_quote_from_yahoo,
    _fetch_yahoo_quotes,
)
from daily_messenger.etl.simulation import (
    simulate_events as _simulate_events,
)
from daily_messenger.etl.simulation import (
    simulate_market_snapshot as _simulate_market_snapshot,
)
from daily_messenger.etl.types import FetchStatus
from daily_messenger.etl.types import QuoteSnapshot as _QuoteSnapshot


@dataclass(frozen=True)
class _EtlPaths:
    raw_market: Path
    raw_events: Path
    status: Path
    marker: Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = PROJECT_ROOT / "out"
STATE_DIR = PROJECT_ROOT / "state"
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
CHINA_TZ = ZoneInfo("Asia/Shanghai")

ALPHA_VANTAGE_SYMBOLS = {
    "SPX": "SPY",  # S&P 500 ETF proxy
    "NDX": "QQQ",  # Nasdaq 100 ETF proxy
}

SECTOR_PROXIES = {
    "AI": "BOTZ",  # Robotics & AI ETF
    "Defensive": "XLP",  # Consumer staples ETF
}

THROTTLE_DISABLED = os.getenv("DM_DISABLE_THROTTLE", "").lower() in {"1", "true", "yes"}


def _sleep(seconds: float) -> None:
    if seconds <= 0 or THROTTLE_DISABLED:
        return
    time.sleep(seconds)


def _ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def _current_trading_day() -> str:
    override = os.getenv("DM_OVERRIDE_DATE")
    if override:
        return override
    now = datetime.now(PACIFIC_TZ)
    return now.strftime("%Y-%m-%d")


AI_NEWS_MARKET_SPECS = ai_news.AI_NEWS_MARKET_SPECS
_AiNewsSettings = ai_news._AiNewsSettings
_resolve_ai_news_settings = ai_news._resolve_ai_news_settings
_extract_gemini_text = ai_news._extract_gemini_text
_extract_glm_text = ai_news._extract_glm_text
_build_market_prompt = ai_news._build_market_prompt

# AI news fetch wrappers live in fetchers/ai_news.py; re-export so the
# orchestration code (and any module.<attr> test stubs) still resolve them here.
from daily_messenger.etl.fetchers.ai_news import (  # noqa: E402
    _fetch_ai_market_news,
    _fetch_gemini_market_news,
)

API_KEYS_CACHE: dict[str, Any] = {}
AI_NEWS_FEEDS: list[str] = list(DEFAULT_AI_FEEDS)
ARXIV_QUERY_PARAMS: dict[str, Any] = dict(DEFAULT_ARXIV_PARAMS)
ARXIV_THROTTLE: float = DEFAULT_ARXIV_THROTTLE

# Preload configuration once at import so module globals reflect runtime hints.
API_KEYS_CACHE, AI_NEWS_FEEDS, ARXIV_QUERY_PARAMS, ARXIV_THROTTLE = _load_configuration()

_fetch_ai_rss_events = ai_news._fetch_ai_rss_events
_fetch_arxiv_events = ai_news._fetch_arxiv_events

_resolve_edgar_user_agent = edgar._resolve_edgar_user_agent
EDGAR_USER_AGENT = edgar.EDGAR_USER_AGENT
_fetch_edgar_fundamentals = edgar._fetch_edgar_fundamentals
_edgar_healthcheck = edgar._edgar_healthcheck


FMP_THEME_SYMBOLS = fmp.FMP_THEME_SYMBOLS
_extract_fmp_metrics = fmp._extract_fmp_metrics
_fetch_fmp_fundamentals = fmp._fetch_fmp_fundamentals


def _fetch_theme_metrics_from_fmp(
    api_keys: dict[str, Any],
) -> tuple[dict[str, Any], FetchStatus]:
    fmp.THROTTLE_DISABLED = THROTTLE_DISABLED
    dependencies = fmp.ThemeMetricDependencies(
        fetch_yahoo_quotes=_fetch_yahoo_quotes,
        fetch_price_only_quotes=_fetch_price_only_quotes,
        fetch_edgar_fundamentals=_fetch_edgar_fundamentals,
        yahoo_allowed=_yahoo_allowed,
    )
    return fmp._fetch_theme_metrics_from_fmp(api_keys, dependencies)


def _resolve_index_quote(symbol: str, api_keys: dict[str, Any]) -> _QuoteSnapshot:
    order_env = os.getenv("QUOTE_ORDER", "")
    default_order = ["stooq", "financial_modeling_prep", "twelve_data", "alpha_vantage"]
    wished = [
        item.strip().lower() for item in order_env.split(",") if item.strip()
    ] or default_order
    fmp_key = _coerce_api_key(api_keys.get("financial_modeling_prep"))
    twelve_key = _coerce_api_key(api_keys.get("twelve_data"))
    alpha_key = _coerce_api_key(api_keys.get("alpha_vantage"))
    allow_yahoo = _yahoo_allowed()

    fetchers: list[tuple[str, Callable[[], _QuoteSnapshot]]] = []
    added: set[str] = set()
    for name in wished:
        if name == "stooq" and "stooq" not in added:
            fetchers.append(("stooq", lambda: _fetch_quote_from_stooq(symbol)))
            added.add("stooq")
        elif name == "financial_modeling_prep" and fmp_key and "fmp" not in added:
            fetchers.append(("fmp", lambda key=fmp_key: _fetch_quote_from_fmp(symbol, key)))
            added.add("fmp")
        elif name == "twelve_data" and twelve_key and "twelve_data" not in added:
            fetchers.append(
                (
                    "twelve_data",
                    lambda key=twelve_key: _fetch_quote_from_twelve_data(symbol, key),
                )
            )
            added.add("twelve_data")
        elif name == "alpha_vantage" and alpha_key and "alpha_vantage" not in added:
            fetchers.append(
                (
                    "alpha_vantage",
                    lambda key=alpha_key: _fetch_quote_from_alpha(symbol, key),
                )
            )
            added.add("alpha_vantage")

    if allow_yahoo:
        fetchers.append(("yahoo", lambda: _fetch_quote_from_yahoo(symbol)))
    return _attempt_quote(fetchers)


def _resolve_equity_quote(symbol: str, api_keys: dict[str, Any]) -> _QuoteSnapshot:
    order_env = os.getenv("QUOTE_ORDER", "")
    default_order = [
        "financial_modeling_prep",
        "twelve_data",
        "stooq",
        "alpaca",
        "alpha_vantage",
    ]
    wished = [
        item.strip().lower() for item in order_env.split(",") if item.strip()
    ] or default_order

    fmp_key = _coerce_api_key(api_keys.get("financial_modeling_prep"))
    twelve_key = _coerce_api_key(api_keys.get("twelve_data"))
    alpha_key = _coerce_api_key(api_keys.get("alpha_vantage"))
    alpaca_key = _coerce_api_key(api_keys.get("alpaca_key_id"))
    alpaca_secret = _coerce_api_key(api_keys.get("alpaca_secret"))
    allow_yahoo = _yahoo_allowed()

    fetchers: list[tuple[str, Callable[[], _QuoteSnapshot]]] = []
    added: set[str] = set()
    for name in wished:
        if name == "financial_modeling_prep" and fmp_key and "fmp" not in added:
            fetchers.append(("fmp", lambda key=fmp_key: _fetch_quote_from_fmp(symbol, key)))
            added.add("fmp")
        elif name == "twelve_data" and twelve_key and "twelve_data" not in added:
            fetchers.append(
                (
                    "twelve_data",
                    lambda key=twelve_key: _fetch_quote_from_twelve_data(symbol, key),
                )
            )
            added.add("twelve_data")
        elif name == "stooq" and "stooq" not in added:
            fetchers.append(("stooq", lambda: _fetch_quote_from_stooq(symbol)))
            added.add("stooq")
        elif name == "alpaca" and alpaca_key and alpaca_secret and "alpaca" not in added:
            fetchers.append(
                (
                    "alpaca",
                    lambda key=alpaca_key, secret=alpaca_secret: _fetch_quote_from_alpaca(
                        symbol, key, secret
                    ),
                )
            )
            added.add("alpaca")
        elif name == "alpha_vantage" and alpha_key and "alpha_vantage" not in added:
            fetchers.append(
                (
                    "alpha_vantage",
                    lambda key=alpha_key: _fetch_quote_from_alpha(symbol, key),
                )
            )
            added.add("alpha_vantage")

    if allow_yahoo:
        fetchers.append(("yahoo", lambda: _fetch_quote_from_yahoo(symbol)))
    return _attempt_quote(fetchers)


def _fetch_market_snapshot_real(
    api_keys: dict[str, Any],
) -> tuple[dict[str, Any] | None, FetchStatus]:
    errors: list[str] = []
    indices: list[dict[str, Any]] = []
    index_sources: dict[str, str] = {}
    latest_date: str | None = None

    for label, proxy in ALPHA_VANTAGE_SYMBOLS.items():
        try:
            snapshot = _resolve_index_quote(proxy, api_keys)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
            continue
        latest_date = latest_date or snapshot.day
        indices.append(
            {
                "symbol": label,
                "close": round(snapshot.close, 2),
                "change_pct": round(snapshot.change_pct, 2),
            }
        )
        index_sources[label] = snapshot.source

    sectors: list[dict[str, Any]] = []
    sector_sources: dict[str, str] = {}
    for name, proxy in SECTOR_PROXIES.items():
        try:
            snapshot = _resolve_equity_quote(proxy, api_keys)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
            continue
        sectors.append({"name": name, "performance": round(1 + snapshot.change_pct / 100, 3)})
        sector_sources[name] = snapshot.source

    if not indices:
        detail = "; ".join(errors) if errors else "无可用行情来源"
        return None, FetchStatus(name="market", ok=False, message=f"美股行情获取失败: {detail}")

    market = {
        "date": latest_date or _current_trading_day(),
        "indices": indices,
        "sectors": sectors,
    }

    parts: list[str] = []
    if index_sources:
        formatted = ", ".join(f"{symbol}:{src}" for symbol, src in index_sources.items())
        parts.append(f"指数来源 {formatted}")
    if sector_sources:
        formatted = ", ".join(f"{name}:{src}" for name, src in sector_sources.items())
        parts.append(f"板块来源 {formatted}")
    if errors:
        parts.append(f"降级 {len(errors)} 项")
    message = "；".join(parts) if parts else "市场行情已获取"
    return market, FetchStatus(name="market", ok=True, message=message)


def _etl_paths(trading_day: str) -> _EtlPaths:
    return _EtlPaths(
        raw_market=OUT_DIR / "raw_market.json",
        raw_events=OUT_DIR / "raw_events.json",
        status=OUT_DIR / "etl_status.json",
        marker=STATE_DIR / f"fetch_{trading_day}",
    )


def _status_cache_matches(path: Path, trading_day: str) -> bool:
    try:
        with path.open("r", encoding="utf-8") as fh:
            status_payload = json.load(fh)
    except Exception:  # noqa: BLE001 - ignore corrupt status cache
        return False
    return isinstance(status_payload, dict) and status_payload.get("date") == trading_day


def _should_skip_cached(paths: _EtlPaths, trading_day: str, force: bool) -> bool:
    if force or not paths.marker.exists():
        return False
    if not (paths.raw_market.exists() and paths.raw_events.exists() and paths.status.exists()):
        return False
    return _status_cache_matches(paths.status, trading_day)


def _load_and_cache_configuration(
    logger: logging.Logger,
) -> tuple[dict[str, Any], list[str], dict[str, Any], float]:
    api_keys, ai_feeds, arxiv_params, arxiv_throttle = _load_configuration(logger)
    global API_KEYS_CACHE, AI_NEWS_FEEDS, ARXIV_QUERY_PARAMS, ARXIV_THROTTLE
    API_KEYS_CACHE = api_keys
    AI_NEWS_FEEDS = ai_feeds
    ARXIV_QUERY_PARAMS = arxiv_params
    ARXIV_THROTTLE = arxiv_throttle
    return api_keys, ai_feeds, arxiv_params, arxiv_throttle


def _load_previous_market_state(raw_market_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    previous_sentiment: dict[str, Any] = {}
    previous_btc: dict[str, Any] = {}
    if not raw_market_path.exists():
        return previous_sentiment, previous_btc
    try:
        with raw_market_path.open("r", encoding="utf-8") as f_prev:
            previous_payload = json.load(f_prev)
    except json.JSONDecodeError:
        return previous_sentiment, previous_btc
    if isinstance(previous_payload, dict):
        prev_sent = previous_payload.get("sentiment")
        if isinstance(prev_sent, dict):
            previous_sentiment = prev_sent
        prev_btc = previous_payload.get("btc")
        if isinstance(prev_btc, dict):
            previous_btc = prev_btc
    return previous_sentiment, previous_btc


def _fetch_base_market_data(
    api_keys: dict[str, Any],
    trading_day: str,
    statuses: list[Any],
) -> tuple[dict[str, Any], bool]:
    market_data, status = _fetch_market_snapshot_real(api_keys)
    statuses.append(status)
    if status.ok:
        return market_data or {}, True

    fallback, fallback_status = _simulate_market_snapshot(trading_day)
    statuses.append(fallback_status)
    return fallback, False


def _merge_hk_market_snapshot(
    api_keys: dict[str, Any],
    market_data: dict[str, Any],
    statuses: list[Any],
) -> bool:
    hk_rows, hk_status = _fetch_hk_market_snapshot(api_keys)
    statuses.append(hk_status)
    if hk_status.ok:
        market_data.setdefault("hk_indices", hk_rows)
        return True
    return False


def _theme_performance_from_market(market_data: Mapping[str, Any]) -> dict[str, Any]:
    theme_metrics: dict[str, Any] = {}
    sectors = market_data.get("sectors", [])
    if isinstance(sectors, list):
        ai_perf = next(
            (
                sector.get("performance")
                for sector in sectors
                if isinstance(sector, dict) and sector.get("name") == "AI"
            ),
            None,
        )
        if ai_perf is not None:
            theme_metrics.setdefault("ai", {})["performance"] = ai_perf
    return theme_metrics


def _merge_theme_market_metrics(
    api_keys: dict[str, Any],
    market_data: dict[str, Any],
    statuses: list[Any],
) -> bool:
    theme_metrics = _theme_performance_from_market(market_data)
    themes, theme_status = _fetch_theme_metrics_from_fmp(api_keys)
    statuses.append(theme_status)
    if theme_status.ok:
        for name, metrics in themes.items():
            theme_metrics.setdefault(name, {}).update(metrics)
    if theme_metrics:
        market_data.setdefault("themes", {}).update(theme_metrics)
    return theme_status.ok


def _fetch_market_payload(
    api_keys: dict[str, Any],
    trading_day: str,
    statuses: list[Any],
) -> tuple[dict[str, Any], bool]:
    market_data, ok = _fetch_base_market_data(api_keys, trading_day, statuses)
    ok = _merge_hk_market_snapshot(api_keys, market_data, statuses) and ok
    ok = _merge_theme_market_metrics(api_keys, market_data, statuses) and ok
    edgar_status = _edgar_healthcheck()
    statuses.append(edgar_status)
    return market_data, ok and edgar_status.ok


# Sentiment merge/aggregate helpers live in fetchers/aaii_sentiment.py; re-export
# so the orchestration code (and any module.<attr> test stubs) still resolve them here.
from daily_messenger.etl.fetchers.aaii_sentiment import (  # noqa: E402
    _fetch_sentiment_payload,
    _merge_sentiment_source,
)


def _fetch_calendar_events(
    trading_day: str,
    api_keys: dict[str, Any],
    statuses: list[Any],
) -> list[dict[str, Any]]:
    events, events_status = _fetch_events_real(trading_day, api_keys)
    statuses.append(events_status)
    if not events_status.ok:
        fallback_events, fallback_status = _simulate_events(trading_day)
        statuses.append(fallback_status)
        return fallback_events

    if api_keys.get("finnhub"):
        finnhub_events, finnhub_status = _fetch_finnhub_earnings(trading_day, api_keys)
        statuses.append(finnhub_status)
        if finnhub_status.ok:
            events.extend(finnhub_events)
    elif api_keys:
        statuses.append(
            FetchStatus(name="finnhub_earnings", ok=False, message="缺少 Finnhub API Key")
        )
    return events


def _fetch_news_events(
    api_keys: dict[str, Any],
    ai_feeds: list[str],
    arxiv_params: dict[str, Any],
    arxiv_throttle: float,
    logger: logging.Logger,
    statuses: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    ai_updates: list[dict[str, Any]] = []
    if ai_feeds:
        ai_events, feed_statuses = _fetch_ai_rss_events(ai_feeds)
        statuses.extend(feed_statuses)
        events.extend(ai_events)
        ai_updates.extend(ai_events)

    if _env_truthy(os.getenv("MARKET_INTEL_SKIP_AI_NEWS")):
        statuses.append(
            FetchStatus(
                name="ai_news",
                ok=True,
                message="skipped by MARKET_INTEL_SKIP_AI_NEWS",
            )
        )
    else:
        ai_news_updates, ai_news_statuses = _fetch_ai_market_news(
            datetime.now(UTC), api_keys, logger
        )
        statuses.extend(ai_news_statuses)
        ai_updates.extend(ai_news_updates)

    arxiv_events, arxiv_status = _fetch_arxiv_events(arxiv_params, arxiv_throttle)
    statuses.append(arxiv_status)
    if arxiv_status.ok:
        events.extend(arxiv_events)
    return events, ai_updates


def _fetch_events_payload(
    trading_day: str,
    api_keys: dict[str, Any],
    ai_feeds: list[str],
    arxiv_params: dict[str, Any],
    arxiv_throttle: float,
    logger: logging.Logger,
    statuses: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events = _fetch_calendar_events(trading_day, api_keys, statuses)
    news_events, ai_updates = _fetch_news_events(
        api_keys, ai_feeds, arxiv_params, arxiv_throttle, logger, statuses
    )
    events.extend(news_events)
    if events:
        events.sort(key=lambda item: (item.get("date"), item.get("impact", "")))
        events = events[:MAX_EVENT_ITEMS]
    return _normalize_raw_events_payload(events, ai_updates)


def _write_etl_outputs(
    paths: _EtlPaths,
    trading_day: str,
    market_payload: dict[str, Any],
    normalized_events: list[dict[str, Any]],
    normalized_ai_updates: list[dict[str, Any]],
    statuses: list[Any],
    overall_ok: bool,
) -> dict[str, Any]:
    with paths.raw_market.open("w", encoding="utf-8") as f:
        json.dump(market_payload, f, ensure_ascii=False, indent=2)
    with paths.raw_events.open("w", encoding="utf-8") as f:
        json.dump(
            {"events": normalized_events, "ai_updates": normalized_ai_updates},
            f,
            ensure_ascii=False,
            indent=2,
        )

    status_payload = {
        "date": trading_day,
        "sources": [asdict(status) for status in statuses],
        "ok": overall_ok,
    }
    with paths.status.open("w", encoding="utf-8") as f:
        json.dump(status_payload, f, ensure_ascii=False, indent=2)
    return status_payload


def _log_etl_statuses(
    logger: logging.Logger,
    statuses: list[Any],
    status_payload: Mapping[str, Any],
) -> None:
    for entry in statuses:
        level = logging.INFO if entry.ok else logging.WARNING
        log(
            logger,
            level,
            "etl_source_status",
            source=entry.name,
            ok=entry.ok,
            detail=entry.message,
        )
    if not status_payload["ok"]:
        log(logger, logging.WARNING, "etl_degraded", reason="one or more fetchers failed")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="强制刷新当日数据")
    args = parser.parse_args(argv)

    started_at = datetime.now(UTC)

    _ensure_out_dir()
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    trading_day = _current_trading_day()
    logger = setup_logger("etl", trading_day=trading_day)
    log(logger, logging.INFO, "etl_start", force=args.force)
    run_meta.record_step(OUT_DIR, "etl", "started", trading_day=trading_day, force=args.force)

    paths = _etl_paths(trading_day)
    if _should_skip_cached(paths, trading_day, args.force):
        log(logger, logging.INFO, "etl_skip_cached")
        run_meta.record_step(OUT_DIR, "etl", "cached", trading_day=trading_day)
        return 0

    log(logger, logging.INFO, "etl_execute", trading_day=trading_day)
    api_keys, ai_feeds, arxiv_params, arxiv_throttle = _load_and_cache_configuration(logger)
    if not api_keys:
        log(logger, logging.WARNING, "etl_missing_api_keys")

    statuses: list[Any] = []
    previous_sentiment, previous_btc = _load_previous_market_state(paths.raw_market)
    market_data, market_ok = _fetch_market_payload(api_keys, trading_day, statuses)
    sentiment_data, sentiment_ok = _fetch_sentiment_payload(previous_sentiment, statuses)
    btc_data, btc_ok = _fetch_btc_payload(api_keys, trading_day, previous_btc, statuses)
    normalized_events, normalized_ai_updates = _fetch_events_payload(
        trading_day,
        api_keys,
        ai_feeds,
        arxiv_params,
        arxiv_throttle,
        logger,
        statuses,
    )
    overall_ok = market_ok and sentiment_ok and btc_ok

    market_payload: dict[str, Any] = {
        "market": market_data,
        "btc": btc_data,
        "sentiment": sentiment_data,
    }
    status_payload = _write_etl_outputs(
        paths,
        trading_day,
        market_payload,
        normalized_events,
        normalized_ai_updates,
        statuses,
        overall_ok,
    )
    _log_etl_statuses(logger, statuses, status_payload)
    paths.marker.touch(exist_ok=True)

    duration = (datetime.now(UTC) - started_at).total_seconds()
    log(
        logger,
        logging.INFO,
        "etl_complete",
        degraded=not status_payload["ok"],
        duration_seconds=round(duration, 2),
        sources=len(statuses),
    )
    run_meta.record_step(
        OUT_DIR,
        "etl",
        "completed",
        trading_day=trading_day,
        degraded=not status_payload["ok"],
        duration_seconds=round(duration, 2),
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
