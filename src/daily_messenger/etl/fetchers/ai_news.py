"""AI market-news fetcher main entry point and backward-compatible re-exports.

This module is the public surface of the AI market-news fetcher. The original
~1300-line implementation has been physically split into smaller submodules
under ``daily_messenger.etl.fetchers`` (``ai_news_common``, ``ai_news_glm``,
``ai_news_gemini``, ``ai_news_aliyun``, ``ai_news_parse``, ``ai_news_feeds``,
``ai_news_settings_chain``). This file keeps only the main
``fetch_market_news_payload`` entry point plus a full set of re-exports so that
every existing ``from ...ai_news import X`` and ``import ...ai_news as m; m.X``
usage keeps working unchanged.

The re-exported names are intended for external callers / tests / monkeypatching
(see ``run_fetch.py``). They are declared in ``__all__`` so the linter recognises
them as the module's public surface instead of treating them as unused.
"""

from __future__ import annotations

__all__ = [
    # 本模块定义
    "fetch_market_news_payload",
    "_fetch_ai_market_news",
    "_fetch_gemini_market_news",
    # re-export：供 run_fetch / 测试 / monkeypatch 通过 ai_news.X 访问
    "AI_NEWS_MARKET_SPECS",
    "_MarketNewsSpec",
    "_request_json",
    "FetchStatus",
    "_resolve_ai_news_settings_chain",
    "_fetch_ai_market_news_real",
    "_call_aliyun_chat_completions",
    "AI_NEWS_PROVIDER_META",
    "ALIYUN_BACKOFF_FACTOR",
    "ALIYUN_BACKOFF_JITTER",
    "ALIYUN_BACKOFF_START",
    "ALIYUN_MAX_RETRIES",
    "CHINA_TZ",
    "GEMINI_BACKOFF_FACTOR",
    "GEMINI_BACKOFF_JITTER",
    "GEMINI_BACKOFF_START",
    "GEMINI_INTER_MARKET_DELAY_RANGE",
    "GEMINI_MAX_RETRIES",
    "GLM_BACKOFF_FACTOR",
    "GLM_BACKOFF_JITTER",
    "GLM_BACKOFF_START",
    "GLM_CHAT_COMPLETIONS_URL",
    "GLM_MAX_RETRIES",
    "GLM_RETRY_STATUS_CODES",
    "THROTTLE_DISABLED",
    "_AiNewsSettings",
    "_build_ai_news_key_queues",
    "_build_market_prompt",
    "_business_day_on_or_before",
    "_filter_market_relevant_items",
    "_format_cn_date",
    "_is_placeholder_source_url",
    "_market_relevance_error",
    "_ParsedMarketNews",
    "_resolve_market_trading_date",
    "_sleep",
    "_fetch_ai_rss_events",
    "_fetch_arxiv_events",
    "_normalize_rss_date",
    "_rss_text",
    "_call_gemini_generate_content",
    "_extract_gemini_text",
    "_call_glm_chat_completions",
    "_extract_glm_text",
    "_build_ai_news_update",
    "_build_ai_news_runtime_manifest",
    "_call_ai_news_provider",
    "_fetch_ai_news_for_market",
    "_parse_market_news_response",
    "_try_ai_news_provider",
    "_fetch_gemini_market_news_real",
    "_collect_ai_news_keys",
    "_first_present",
    "_provider_label",
    "_resolve_ai_news_settings",
    "_resolve_aliyun_endpoint",
    "_resolve_direct_connection",
    "_resolve_enable_network",
    "_resolve_extra_instructions",
    "_resolve_model",
    "_resolve_thinking",
    "_resolve_timeout",
    "_settings_from_parts",
]

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from daily_messenger.common.logging import log
from daily_messenger.common.market_news import (
    AI_NEWS_MARKET_SPECS,
)
from daily_messenger.common.market_news import (
    MarketNewsSpec as _MarketNewsSpec,
)
from daily_messenger.etl.http import request_json as _request_json
from daily_messenger.etl.types import FetchStatus

from .ai_news_aliyun import (
    _call_aliyun_chat_completions,
)
from .ai_news_common import (
    AI_NEWS_PROVIDER_META,
    ALIYUN_BACKOFF_FACTOR,
    ALIYUN_BACKOFF_JITTER,
    ALIYUN_BACKOFF_START,
    ALIYUN_MAX_RETRIES,
    CHINA_TZ,
    GEMINI_BACKOFF_FACTOR,
    GEMINI_BACKOFF_JITTER,
    GEMINI_BACKOFF_START,
    GEMINI_INTER_MARKET_DELAY_RANGE,
    GEMINI_MAX_RETRIES,
    GLM_BACKOFF_FACTOR,
    GLM_BACKOFF_JITTER,
    GLM_BACKOFF_START,
    GLM_CHAT_COMPLETIONS_URL,
    GLM_MAX_RETRIES,
    GLM_RETRY_STATUS_CODES,
    THROTTLE_DISABLED,
    _AiNewsSettings,
    _build_ai_news_key_queues,
    _build_market_prompt,
    _business_day_on_or_before,
    _filter_market_relevant_items,
    _format_cn_date,
    _is_placeholder_source_url,
    _market_relevance_error,
    _ParsedMarketNews,
    _resolve_market_trading_date,
    _sleep,
)
from .ai_news_feeds import (
    _fetch_ai_rss_events,
    _fetch_arxiv_events,
    _normalize_rss_date,
    _rss_text,
)
from .ai_news_gemini import (
    _call_gemini_generate_content,
    _extract_gemini_text,
)
from .ai_news_glm import (
    _call_glm_chat_completions,
    _extract_glm_text,
)
from .ai_news_parse import (
    _build_ai_news_update,
    _call_ai_news_provider,
    _fetch_ai_news_for_market,
    _parse_market_news_response,
    _try_ai_news_provider,
)
from .ai_news_parse import (
    _fetch_ai_market_news as _fetch_ai_market_news_real,
)
from .ai_news_parse import (
    _fetch_gemini_market_news as _fetch_gemini_market_news_real,
)
from .ai_news_settings_chain import (
    _collect_ai_news_keys,
    _first_present,
    _provider_label,
    _resolve_ai_news_settings,
    _resolve_ai_news_settings_chain,
    _resolve_aliyun_endpoint,
    _resolve_direct_connection,
    _resolve_enable_network,
    _resolve_extra_instructions,
    _resolve_model,
    _resolve_thinking,
    _resolve_timeout,
    _settings_from_parts,
)


def fetch_market_news_payload(
    markets: Sequence[str] | None = None,
    *,
    api_keys: dict[str, Any] | None = None,
    now_utc: datetime | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Fetch structured market news and return the cron JSON contract payload."""
    if api_keys is None:
        from daily_messenger.etl.config import load_configuration

        api_keys, _, _, _ = load_configuration(logger)

    requested = [
        market.strip().lower()
        for market in (markets or [spec.market for spec in AI_NEWS_MARKET_SPECS])
        if market.strip()
    ]
    requested_set = set(requested)
    specs_by_market = {spec.market: spec for spec in AI_NEWS_MARKET_SPECS}
    settings_chain = _resolve_ai_news_settings_chain(api_keys)
    _log_ai_news_runtime(logger, settings_chain)
    primary_settings = settings_chain[0] if settings_chain else None
    provider_label = primary_settings.provider if primary_settings else ""
    model = primary_settings.model if primary_settings else ""

    updates, statuses = _fetch_ai_market_news_real(
        now_utc or datetime.now(UTC),
        api_keys,
        logger,
        market_codes=requested_set,
    )

    markets_payload: dict[str, dict[str, Any]] = {}
    for market in requested:
        spec = specs_by_market.get(market)
        if spec is None:
            markets_payload[market] = {"market": market, "error": "unknown market"}
            continue
        markets_payload[market] = {
            "market": spec.market,
            "label": spec.label,
            "scope": spec.scope,
        }

    for update in updates:
        market = str(update.get("market") or "")
        if not market:
            continue
        entry = markets_payload.setdefault(market, {"market": market})
        entry.update(
            {
                "date": update.get("date", ""),
                "provider": update.get("provider", provider_label),
                "model": update.get("model", model),
                "news_text": update.get("summary", ""),
            }
        )
        if update.get("items"):
            entry["items"] = update["items"]
        if update.get("rejected_items"):
            entry["rejected_items"] = update["rejected_items"]
        if update.get("fallback_errors"):
            entry["fallback_errors"] = update["fallback_errors"]

    for status in statuses:
        if status.ok or not status.name.startswith("ai_news_"):
            continue
        market = status.name.removeprefix("ai_news_")
        if market in markets_payload:
            markets_payload[market]["error"] = status.message

    payload: dict[str, Any] = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "provider": provider_label,
        "model": model,
        "providers": [
            {
                "provider": settings.provider,
                "model": settings.model,
                "configured": bool(settings.keys),
                "direct_connection": settings.direct_connection,
            }
            for settings in settings_chain
        ],
        "markets_requested": requested,
        "markets": markets_payload,
    }
    if primary_settings is None:
        payload["error"] = "AI market news is not configured"
    return payload


def _build_ai_news_runtime_manifest(
    settings_chain: list[_AiNewsSettings],
) -> dict[str, Any]:
    """Return non-secret metadata for the resolved AI-news provider chain."""
    if not settings_chain:
        return {
            "provider": "",
            "model": "",
            "base_url": "",
            "fallback_order": [],
        }

    primary = settings_chain[0]
    return {
        "provider": primary.provider,
        "model": primary.model,
        "base_url": primary.base_url or "",
        "fallback_order": [settings.provider for settings in settings_chain[1:]],
    }


def _log_ai_news_runtime(
    logger: logging.Logger | None,
    settings_chain: list[_AiNewsSettings],
) -> None:
    if logger:
        log(
            logger,
            logging.INFO,
            "ai_news_runtime",
            **_build_ai_news_runtime_manifest(settings_chain),
        )


def _fetch_ai_market_news(
    now_utc: datetime,
    api_keys: dict[str, Any],
    logger: logging.Logger | None,
) -> tuple[list[dict[str, Any]], list[FetchStatus]]:
    """Run-fetch orchestration entrypoint for AI market news.

    Moved out of ``run_fetch`` so the ETL entrypoint can simply re-export this
    name. The original ``run_fetch`` wrapper only performed a no-op call-provider
    monkeypatch (the referenced call functions are the module-level real
    implementations), so we delegate directly to the real fetcher here.
    """
    return _fetch_ai_market_news_real(now_utc, api_keys, logger)


def _fetch_gemini_market_news(
    now_utc: datetime,
    api_keys: dict[str, Any],
    logger: logging.Logger | None,
) -> tuple[list[dict[str, Any]], list[FetchStatus]]:
    """Backward compatible wrapper."""
    return _fetch_ai_market_news(now_utc, api_keys, logger)
