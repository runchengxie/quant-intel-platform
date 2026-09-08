"""Aliyun (DashScope / BaiLian) provider call for the AI market-news fetcher.

Pure physical split-out of ``ai_news.py``. Depends only on ``ai_news_common``
and the low-level HTTP helper. The Aliyun chat-completions endpoint returns a
GLM-style payload, so response text is extracted with
``ai_news_glm._extract_glm_text`` as in the original module.
"""

from __future__ import annotations

from typing import Any

from daily_messenger.etl.config import (
    DEFAULT_ALIYUN_BASE_URL,
    DEFAULT_ALIYUN_DIRECT_CONNECTION,
    DEFAULT_ALIYUN_SEARCH_STRATEGY,
)
from daily_messenger.etl.http import (
    USER_AGENT,
    RetryPolicy,
)

from . import ai_news as _an
from .ai_news_common import (
    ALIYUN_BACKOFF_FACTOR,
    ALIYUN_BACKOFF_JITTER,
    ALIYUN_BACKOFF_START,
    ALIYUN_MAX_RETRIES,
)


def _call_aliyun_chat_completions(
    model: str,
    api_key: str,
    prompt: str,
    enable_network: bool,
    timeout: float,
    base_url: str | None,
    search_strategy: str | None,
    direct_connection: bool = DEFAULT_ALIYUN_DIRECT_CONNECTION,
) -> dict[str, Any]:
    resolved_base = (base_url or DEFAULT_ALIYUN_BASE_URL).rstrip("/")
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    if enable_network:
        body["enable_search"] = True
        strategy = (search_strategy or DEFAULT_ALIYUN_SEARCH_STRATEGY).strip()
        if strategy:
            body["search_options"] = {"search_strategy": strategy}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    per_request_timeout = max(timeout, 5.0)
    hard_deadline = max(per_request_timeout * 2.5, per_request_timeout + 10.0)
    policy = RetryPolicy(
        retries=ALIYUN_MAX_RETRIES,
        backoff_start=ALIYUN_BACKOFF_START,
        backoff_factor=ALIYUN_BACKOFF_FACTOR,
        jitter=ALIYUN_BACKOFF_JITTER,
        max_sleep=8.0,
        per_request_timeout=per_request_timeout,
        hard_deadline=hard_deadline,
    )
    payload = _an._request_json(
        f"{resolved_base}/chat/completions",
        method="POST",
        json_body=body,
        headers=headers,
        policy=policy,
        trust_env=not direct_connection,
    )
    if not isinstance(payload, dict):
        raise ValueError("Aliyun 响应不是 JSON 对象")
    return payload
