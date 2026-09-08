"""Response parsing and the per-market / aggregate fetch orchestration.

Pure physical split-out of ``ai_news.py``. The provider-call dispatch
(``_call_ai_news_provider``) intentionally resolves the callables through the
``ai_news`` package namespace at call time, so that ``run_fetch`` can monkeypatch
``ai_news._call_glm_chat_completions`` / ``ai_news._call_gemini_generate_content``
at runtime and have it take effect.
"""

from __future__ import annotations

import logging
import random
from collections import deque
from datetime import datetime
from typing import Any

import requests

from daily_messenger.common.logging import log
from daily_messenger.common.market_news import MarketNewsSpec as _MarketNewsSpec
from daily_messenger.common.news_contract import (
    normalize_news_items,
    parse_news_items_from_text,
    render_news_text,
)
from daily_messenger.etl.config import (
    AI_NEWS_PROVIDER_ALIYUN,
    AI_NEWS_PROVIDER_GLM,
)
from daily_messenger.etl.http import sleep_exact as _sleep_exact
from daily_messenger.etl.types import FetchStatus

from . import ai_news as _an
from .ai_news_common import (
    AI_NEWS_PROVIDER_META,
    CHINA_TZ,
    GEMINI_INTER_MARKET_DELAY_RANGE,
    _AiNewsSettings,
    _build_ai_news_key_queues,
    _build_market_prompt,
    _filter_market_relevant_items,
    _ParsedMarketNews,
    _resolve_market_trading_date,
)
from .ai_news_settings_chain import (
    _provider_label,
    _resolve_ai_news_settings_chain,
)

logger = logging.getLogger(__name__)


def _call_ai_news_provider(settings: _AiNewsSettings, token: str, prompt: str) -> str:
    # The callables are resolved through the ``ai_news`` package namespace at
    # call time so that ``run_fetch`` can monkeypatch
    # ``ai_news._call_glm_chat_completions`` / ``ai_news._call_gemini_generate_content``.
    if settings.provider == AI_NEWS_PROVIDER_GLM:
        payload = _an._call_glm_chat_completions(
            settings.model,
            token,
            prompt,
            settings.enable_network,
            settings.timeout,
            settings.thinking,
            settings.direct_connection,
        )
        return _an._extract_glm_text(payload)
    if settings.provider == AI_NEWS_PROVIDER_ALIYUN:
        payload = _an._call_aliyun_chat_completions(
            settings.model,
            token,
            prompt,
            settings.enable_network,
            settings.timeout,
            settings.base_url,
            settings.search_strategy,
            settings.direct_connection,
        )
        return _an._extract_glm_text(payload)

    payload = _an._call_gemini_generate_content(
        settings.model,
        token,
        prompt,
        settings.enable_network,
        settings.timeout,
        settings.direct_connection,
    )
    return _an._extract_gemini_text(payload)


def _try_ai_news_provider(
    spec: _MarketNewsSpec,
    target_day: datetime,
    beijing_now: datetime,
    settings: _AiNewsSettings,
    key_queue: deque[tuple[str, str]],
    error_messages: list[str],
) -> str:
    provider_label = _provider_label(settings.provider)
    if not key_queue:
        error_messages.append(f"{provider_label}: API key 已耗尽或未配置")
        return ""

    prompt = _build_market_prompt(spec, target_day, beijing_now, settings)
    for _ in range(len(key_queue)):
        label, token = key_queue[0]
        try:
            text = _call_ai_news_provider(settings, token, prompt)
        except requests.HTTPError as exc:
            error_messages.append(f"{provider_label}/{label}: HTTP {exc}")
            key_queue.rotate(-1)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("_try_ai_news_provider" + " 捕获到异常", exc_info=True)
            error_messages.append(f"{provider_label}/{label}: {exc}")
            key_queue.rotate(-1)
            continue

        key_queue.rotate(-1)
        if text:
            return text
        error_messages.append(f"{provider_label}/{label}: 空响应")
    return ""


def _parse_market_news_response(
    response_text: str,
    spec: _MarketNewsSpec,
    target_day: datetime,
) -> tuple[_ParsedMarketNews | None, str]:
    from daily_messenger.common.market_news import extract_news_section

    candidate_section = extract_news_section(response_text)
    if not candidate_section:
        return None, "响应缺少 <news> 内容"

    raw_items = parse_news_items_from_text(response_text)
    candidate_items, candidate_errors = normalize_news_items(
        raw_items,
        market=spec.market,
        label=spec.label,
        fallback_published_at=target_day.date().isoformat(),
        max_items=5,
        require_url=True,
    )
    candidate_items, relevance_errors = _filter_market_relevant_items(
        candidate_items,
        market=spec.market,
    )
    candidate_errors.extend(relevance_errors)
    if not candidate_items:
        detail = "；".join(candidate_errors[-3:]) if candidate_errors else ""
        suffix = f"（{detail}）" if detail else ""
        return None, f"未返回通过校验的结构化新闻{suffix}"

    summary = render_news_text(candidate_items)
    return (
        _ParsedMarketNews(
            news_section=candidate_section,
            items=candidate_items,
            item_errors=candidate_errors,
            summary=summary,
        ),
        "",
    )


def _build_ai_news_update(
    spec: _MarketNewsSpec,
    target_day: datetime,
    beijing_now: datetime,
    settings: _AiNewsSettings,
    parsed: _ParsedMarketNews,
    error_messages: list[str],
) -> dict[str, Any]:
    provider_meta = AI_NEWS_PROVIDER_META.get(
        settings.provider,
        {"source": settings.provider, "provider": settings.provider},
    )
    update: dict[str, Any] = {
        "title": f"{spec.label} {target_day.date().isoformat()} 交易日资讯",
        "market": spec.market,
        "date": target_day.date().isoformat(),
        "summary": parsed.summary,
        "source": provider_meta["source"],
        "provider": provider_meta["provider"],
        "model": settings.model,
        "prompt_scope": spec.scope,
        "prompt_date": target_day.date().isoformat(),
        "requested_beijing": beijing_now.isoformat(),
        "raw_text": parsed.news_section,
        "structured": bool(parsed.items),
    }
    if error_messages:
        update["fallback_errors"] = error_messages[-5:]
    if parsed.items:
        update["items"] = parsed.items
    if parsed.item_errors:
        update["rejected_items"] = parsed.item_errors[:5]
    return update


def _fetch_ai_news_for_market(
    spec: _MarketNewsSpec,
    now_utc: datetime,
    beijing_now: datetime,
    settings_chain: list[_AiNewsSettings],
    key_queues: dict[str, deque[tuple[str, str]]],
    logger: logging.Logger | None,
) -> tuple[dict[str, Any] | None, FetchStatus]:
    target_day = _resolve_market_trading_date(now_utc, spec)
    error_messages: list[str] = []

    for settings in settings_chain:
        response_text = _try_ai_news_provider(
            spec,
            target_day,
            beijing_now,
            settings,
            key_queues.get(settings.provider, deque()),
            error_messages,
        )
        if not response_text:
            continue

        parsed, parse_error = _parse_market_news_response(response_text, spec, target_day)
        if parsed is None:
            error_messages.append(f"{_provider_label(settings.provider)}: {parse_error}")
            continue

        update = _build_ai_news_update(
            spec, target_day, beijing_now, settings, parsed, error_messages
        )
        if logger:
            log(
                logger,
                logging.INFO,
                "ai_news_generated",
                market=spec.market,
                prompt_date=update["prompt_date"],
                provider=settings.provider,
            )
        return (
            update,
            FetchStatus(
                name=f"ai_news_{spec.market}",
                ok=True,
                message=f"{spec.label} 摘要生成成功",
            ),
        )

    detail = "；".join(error_messages[-5:]) if error_messages else "未知错误"
    return (
        None,
        FetchStatus(
            name=f"ai_news_{spec.market}",
            ok=False,
            message=f"{spec.label} 摘要生成失败（{detail}）",
        ),
    )


def _fetch_ai_market_news(
    now_utc: datetime,
    api_keys: dict[str, Any],
    logger: logging.Logger | None,
    market_codes: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[FetchStatus]]:
    settings_chain = _resolve_ai_news_settings_chain(api_keys)
    if not settings_chain:
        return (
            [],
            [
                FetchStatus(
                    name="ai_news",
                    ok=True,
                    message="AI 市场资讯未配置，跳过摘要生成",
                )
            ],
        )

    updates: list[dict[str, Any]] = []
    statuses: list[FetchStatus] = []
    if not any(settings.keys for settings in settings_chain):
        provider_labels = "/".join(
            _provider_label(settings.provider) for settings in settings_chain
        )
        return (
            updates,
            [
                FetchStatus(
                    name="ai_news",
                    ok=False,
                    message=f"{provider_labels} 未提供可用的 API key",
                )
            ],
        )

    selected_specs = [
        spec
        for spec in _an.AI_NEWS_MARKET_SPECS
        if market_codes is None or spec.market in market_codes
    ]
    key_queues = _build_ai_news_key_queues(settings_chain)
    beijing_now = now_utc.astimezone(CHINA_TZ)

    for index, spec in enumerate(selected_specs):
        if index > 0 and not _an.THROTTLE_DISABLED:
            lower, upper = GEMINI_INTER_MARKET_DELAY_RANGE
            _sleep_exact(random.uniform(lower, upper))

        update, status = _fetch_ai_news_for_market(
            spec,
            now_utc,
            beijing_now,
            settings_chain,
            key_queues,
            logger,
        )
        if update is not None:
            updates.append(update)
        statuses.append(status)

    return updates, statuses


def _fetch_gemini_market_news(
    now_utc: datetime,
    api_keys: dict[str, Any],
    logger: logging.Logger | None,
) -> tuple[list[dict[str, Any]], list[FetchStatus]]:
    """Backward compatible wrapper."""
    return _fetch_ai_market_news(now_utc, api_keys, logger)
