"""GLM (Zhipu) provider call + response extraction for the AI market-news fetcher.

Pure physical split-out of ``ai_news.py``. This module depends only on the
shared constants/helpers in ``ai_news_common`` and the low-level HTTP helper.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from daily_messenger.etl.config import (
    DEFAULT_GLM_DIRECT_CONNECTION,
)
from daily_messenger.etl.http import (
    USER_AGENT,
    RetryPolicy,
)

from . import ai_news as _an
from .ai_news_common import (
    GLM_BACKOFF_FACTOR,
    GLM_BACKOFF_JITTER,
    GLM_BACKOFF_START,
    GLM_CHAT_COMPLETIONS_URL,
    GLM_MAX_RETRIES,
    GLM_RETRY_STATUS_CODES,
)


def _call_glm_chat_completions(
    model: str,
    api_key: str,
    prompt: str,
    enable_network: bool,
    timeout: float,
    thinking: str | None,
    direct_connection: bool = DEFAULT_GLM_DIRECT_CONNECTION,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    if thinking:
        body["thinking"] = {"type": thinking}
    if enable_network:
        body["tools"] = [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_result": True,
                },
            }
        ]
        body["tool_choice"] = "auto"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    per_request_timeout = max(timeout, 5.0)
    hard_deadline = max(per_request_timeout * 2.5, per_request_timeout + 10.0)
    policy = RetryPolicy(
        retries=GLM_MAX_RETRIES,
        backoff_start=GLM_BACKOFF_START,
        backoff_factor=GLM_BACKOFF_FACTOR,
        jitter=GLM_BACKOFF_JITTER,
        status_forcelist=GLM_RETRY_STATUS_CODES,
        max_sleep=8.0,
        per_request_timeout=per_request_timeout,
        hard_deadline=hard_deadline,
    )
    payload = _an._request_json(
        GLM_CHAT_COMPLETIONS_URL,
        method="POST",
        json_body=body,
        headers=headers,
        policy=policy,
        trust_env=not direct_connection,
    )
    if not isinstance(payload, dict):
        raise ValueError("GLM 响应不是 JSON 对象")
    return payload


def _extract_glm_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return ""
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if isinstance(content, str):
            content = content.strip()
            if content:
                return content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, Mapping):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
    return ""
