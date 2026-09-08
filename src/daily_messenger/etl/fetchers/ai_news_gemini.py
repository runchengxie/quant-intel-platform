"""Gemini (Google) provider call + response extraction for the AI market-news fetcher.

Pure physical split-out of ``ai_news.py``. Depends only on ``ai_news_common``
and the low-level HTTP helper.
"""

from __future__ import annotations

from typing import Any

from daily_messenger.etl.config import (
    DEFAULT_GEMINI_DIRECT_CONNECTION,
)
from daily_messenger.etl.http import (
    USER_AGENT,
    RetryPolicy,
)

from . import ai_news as _an
from .ai_news_common import (
    GEMINI_BACKOFF_FACTOR,
    GEMINI_BACKOFF_JITTER,
    GEMINI_BACKOFF_START,
    GEMINI_MAX_RETRIES,
)


def _call_gemini_generate_content(
    model: str,
    api_key: str,
    prompt: str,
    enable_network: bool,
    timeout: float,
    direct_connection: bool = DEFAULT_GEMINI_DIRECT_CONNECTION,
) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    params = {"key": api_key}
    body: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt,
                    }
                ],
            }
        ]
    }
    if enable_network:
        body["tools"] = [{"googleSearchRetrieval": {}}]
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    }
    per_request_timeout = max(timeout, 5.0)
    hard_deadline = max(per_request_timeout * 2.5, per_request_timeout + 10.0)
    policy = RetryPolicy(
        retries=GEMINI_MAX_RETRIES,
        backoff_start=GEMINI_BACKOFF_START,
        backoff_factor=GEMINI_BACKOFF_FACTOR,
        jitter=GEMINI_BACKOFF_JITTER,
        max_sleep=8.0,
        per_request_timeout=per_request_timeout,
        hard_deadline=hard_deadline,
    )
    payload = _an._request_json(
        url,
        method="POST",
        params=params,
        json_body=body,
        headers=headers,
        policy=policy,
        trust_env=not direct_connection,
    )
    if not isinstance(payload, dict):
        raise ValueError("Gemini 响应不是 JSON 对象")
    return payload


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return ""
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    return ""
