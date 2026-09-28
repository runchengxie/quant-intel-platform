"""Small server-side clients; bounded retries and no credentials in artifacts."""

from __future__ import annotations

import json
import re
import time
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CLAIM = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "evidence_ids"],
    "additionalProperties": False,
}
ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overview": CLAIM,
        "changes": {"type": "array", "items": CLAIM},
        "tensions": {"type": "array", "items": CLAIM},
        "watchpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "question": {"type": "string"},
                    "metric": {
                        "type": "string",
                        "enum": ["advancing_pct", "volume_ratio", "tail_loss_pct", "above_vwap_pct"],
                    },
                    "operator": {"type": "string", "enum": [">", "<", ">=", "<="]},
                    "threshold": {"type": "number"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question", "metric", "operator", "threshold", "evidence_ids"],
            },
        },
    },
    "required": ["overview", "changes", "tensions", "watchpoints"],
}


class ProviderHTTPError(HTTPError):
    """Sanitized HTTP failure with explicitly typed public diagnostics."""

    def __init__(self, code: int, diagnostics: dict[str, int | str]) -> None:
        super().__init__("", code, "provider request failed", Message(), None)
        self.diagnostics = diagnostics
        self.close()


def _safe_http_error(exc: HTTPError) -> ProviderHTTPError:
    """Expose fixed diagnostic codes, never URLs, server prose, or metadata."""
    diagnostics: dict[str, int | str] = {"http_status": exc.code}
    statuses = {
        "INVALID_ARGUMENT",
        "UNAUTHENTICATED",
        "PERMISSION_DENIED",
        "NOT_FOUND",
        "RESOURCE_EXHAUSTED",
        "FAILED_PRECONDITION",
        "INTERNAL",
        "UNAVAILABLE",
    }
    reasons = {
        "API_KEY_INVALID",
        "API_KEY_EXPIRED",
        "API_KEY_SERVICE_BLOCKED",
        "API_KEY_HTTP_REFERRER_BLOCKED",
        "API_KEY_IP_ADDRESS_BLOCKED",
        "API_KEY_ANDROID_APP_BLOCKED",
        "API_KEY_IOS_APP_BLOCKED",
        "SERVICE_DISABLED",
        "BILLING_DISABLED",
        "CONSUMER_INVALID",
        "RATE_LIMIT_EXCEEDED",
    }
    try:
        payload = json.loads(exc.read(65537))
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            status = error.get("status")
            if isinstance(status, str) and status in statuses:
                diagnostics["api_status"] = status
            details = error.get("details", [])
            for detail in details if isinstance(details, list) else []:
                reason = detail.get("reason") if isinstance(detail, dict) else None
                if isinstance(reason, str) and reason in reasons:
                    diagnostics["reason"] = reason
                    break
            message = error.get("message", "")
            if isinstance(message, str):
                lowered = message.lower()
                for fragment, code in (
                    ("user location is not supported", "unsupported_region"),
                    ("responsejsonschema", "request_schema_rejected"),
                    ("api key not valid", "invalid_api_key"),
                ):
                    if fragment in lowered and "reason" not in diagnostics:
                        diagnostics["category"] = code
                        break
    except (OSError, ValueError):
        pass
    finally:
        exc.close()
    return ProviderHTTPError(exc.code, diagnostics)


def _request(context: dict, prompt: str, provider: str, model: str, api_key: str) -> Request:
    user = json.dumps(context, ensure_ascii=False)
    if len(user) > 120000:
        raise ValueError("source context exceeds configured limit")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ValueError("invalid model identifier")
    if provider == "gemini":
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
                "responseJsonSchema": ANALYSIS_SCHEMA,
            },
        }
        headers = {"x-goog-api-key": api_key}
    elif provider in {"minimax", "deepseek"}:
        endpoint = (
            "https://api.minimax.io/v1/chat/completions"
            if provider == "minimax"
            else "https://api.deepseek.com/chat/completions"
        )
        body = {
            "model": model,
            "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": user}],
            "temperature": 0.3,
            "max_tokens": 8192,
        }
        if provider == "deepseek":
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        raise ValueError("unsupported provider")
    return Request(
        endpoint,
        data=json.dumps(body).encode(),
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )


def _fetch(request: Request) -> dict:
    attempt = 0
    while True:
        try:
            with urlopen(request, timeout=45) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("oversized provider response")
            return json.loads(raw)
        except HTTPError as exc:
            if attempt == 2 or (exc.code != 429 and not 500 <= exc.code < 600):
                raise _safe_http_error(exc) from None
            exc.close()
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2**attempt)
        attempt += 1


def _decode(payload: dict, provider: str) -> dict:
    if provider == "gemini":
        candidate = payload["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("incomplete Gemini response")
        text = "".join(
            part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought")
        )
    else:
        choice = payload["choices"][0]
        if choice.get("finish_reason", "stop") != "stop":
            raise ValueError("incomplete MiniMax response")
        text = re.sub(r"<think>.*?</think>", "", choice["message"]["content"], flags=re.DOTALL).strip()
        if text.startswith("```json") and text.endswith("```"):
            text = text[7:-3].strip()
    return json.loads(text)


def generate(context: dict, prompt: str, provider: str, model: str, api_key: str) -> dict:
    return _decode(_fetch(_request(context, prompt, provider, model, api_key)), provider)
