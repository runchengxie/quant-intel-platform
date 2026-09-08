"""Table-driven helpers for AI market-news provider configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from daily_messenger.etl.config import (
    AI_NEWS_PROVIDER_ALIYUN,
    AI_NEWS_PROVIDER_GEMINI,
    AI_NEWS_PROVIDER_GLM,
    DEFAULT_AI_NEWS_PROVIDER,
    DEFAULT_ALIYUN_DIRECT_CONNECTION,
    DEFAULT_ALIYUN_ENABLE_NETWORK,
    DEFAULT_ALIYUN_MODEL,
    DEFAULT_ALIYUN_TIMEOUT,
    DEFAULT_GEMINI_DIRECT_CONNECTION,
    DEFAULT_GEMINI_ENABLE_NETWORK,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_TIMEOUT,
    DEFAULT_GLM_DIRECT_CONNECTION,
    DEFAULT_GLM_ENABLE_NETWORK,
    DEFAULT_GLM_MODEL,
    DEFAULT_GLM_TIMEOUT,
    env_truthy,
)


@dataclass(frozen=True)
class ProviderDefaults:
    model: str
    timeout: float
    enable_network: bool
    direct_connection: bool
    model_field: str


PROVIDER_DEFAULTS: dict[str, ProviderDefaults] = {
    AI_NEWS_PROVIDER_GLM: ProviderDefaults(
        model=DEFAULT_GLM_MODEL,
        timeout=DEFAULT_GLM_TIMEOUT,
        enable_network=DEFAULT_GLM_ENABLE_NETWORK,
        direct_connection=DEFAULT_GLM_DIRECT_CONNECTION,
        model_field="glm_model",
    ),
    AI_NEWS_PROVIDER_ALIYUN: ProviderDefaults(
        model=DEFAULT_ALIYUN_MODEL,
        timeout=DEFAULT_ALIYUN_TIMEOUT,
        enable_network=DEFAULT_ALIYUN_ENABLE_NETWORK,
        direct_connection=DEFAULT_ALIYUN_DIRECT_CONNECTION,
        model_field="aliyun_model",
    ),
    AI_NEWS_PROVIDER_GEMINI: ProviderDefaults(
        model=DEFAULT_GEMINI_MODEL,
        timeout=DEFAULT_GEMINI_TIMEOUT,
        enable_network=DEFAULT_GEMINI_ENABLE_NETWORK,
        direct_connection=DEFAULT_GEMINI_DIRECT_CONNECTION,
        model_field="gemini_model",
    ),
}

PROVIDER_LABELS = {
    AI_NEWS_PROVIDER_GLM: "GLM",
    AI_NEWS_PROVIDER_ALIYUN: "Aliyun",
    AI_NEWS_PROVIDER_GEMINI: "Gemini",
}

PROVIDER_ALIASES: dict[str, str] = {
    AI_NEWS_PROVIDER_ALIYUN: AI_NEWS_PROVIDER_ALIYUN,
    "alibaba": AI_NEWS_PROVIDER_ALIYUN,
    "alibaba_bailian": AI_NEWS_PROVIDER_ALIYUN,
    "bailian": AI_NEWS_PROVIDER_ALIYUN,
    "dashscope": AI_NEWS_PROVIDER_ALIYUN,
    "modelstudio": AI_NEWS_PROVIDER_ALIYUN,
    "model_studio": AI_NEWS_PROVIDER_ALIYUN,
    "qwen": AI_NEWS_PROVIDER_ALIYUN,
    "tongyi": AI_NEWS_PROVIDER_ALIYUN,
    "tongyiqianwen": AI_NEWS_PROVIDER_ALIYUN,
    AI_NEWS_PROVIDER_GLM: AI_NEWS_PROVIDER_GLM,
    "zhipu": AI_NEWS_PROVIDER_GLM,
    "zhipuai": AI_NEWS_PROVIDER_GLM,
    "glm4": AI_NEWS_PROVIDER_GLM,
    "glm-4.6": AI_NEWS_PROVIDER_GLM,
    "glm4.6": AI_NEWS_PROVIDER_GLM,
    "bigmodel": AI_NEWS_PROVIDER_GLM,
    AI_NEWS_PROVIDER_GEMINI: AI_NEWS_PROVIDER_GEMINI,
    "google": AI_NEWS_PROVIDER_GEMINI,
    "google_gemini": AI_NEWS_PROVIDER_GEMINI,
    "gemini-pro": AI_NEWS_PROVIDER_GEMINI,
    "gemini-pro-vision": AI_NEWS_PROVIDER_GEMINI,
    "gemini-2.5-pro": AI_NEWS_PROVIDER_GEMINI,
}

PROVIDER_MODEL_MARKERS = {
    AI_NEWS_PROVIDER_GEMINI: ("gemini",),
    AI_NEWS_PROVIDER_ALIYUN: ("qwen", "dashscope", "bailian"),
    AI_NEWS_PROVIDER_GLM: ("glm", "zhipu"),
}

PROVIDER_KEY_PREFIXES = {
    AI_NEWS_PROVIDER_GEMINI: ("gemini", "google_gemini"),
    AI_NEWS_PROVIDER_ALIYUN: (
        "aliyun",
        "alibaba",
        "alibaba_bailian",
        "bailian",
        "dashscope",
        "qwen",
    ),
    AI_NEWS_PROVIDER_GLM: ("glm", "zhipu", "zhipuai", "zai", "bigmodel"),
}

PROVIDER_SECTION_HINTS = {
    AI_NEWS_PROVIDER_GEMINI: ("gemini_model", "gemini_enable_network", "google_search"),
    AI_NEWS_PROVIDER_ALIYUN: (
        "aliyun_model",
        "aliyun_enable_network",
        "aliyun_base_url",
        "aliyun_search_strategy",
    ),
    AI_NEWS_PROVIDER_GLM: ("glm_model", "glm_enable_network", "glm_thinking"),
}

PROVIDER_METADATA_SUFFIXES = (
    "_model",
    "model",
    "enable_network",
    "direct_connection",
    "disable_proxy",
    "no_proxy",
    "extra_prompt",
    "base_url",
    "search_strategy",
    "thinking",
)


def parse_ai_news_section(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return dict(value) if isinstance(value, Mapping) else None


def normalize_provider(candidate: Any) -> str | None:
    if not isinstance(candidate, str):
        return None
    return PROVIDER_ALIASES.get(candidate.strip().lower())


def infer_provider_from_model(model_value: Any) -> str | None:
    if not isinstance(model_value, str):
        return None
    lowered = model_value.strip().lower()
    if not lowered:
        return None
    for provider, markers in PROVIDER_MODEL_MARKERS.items():
        if any(marker in lowered for marker in markers):
            return provider
    return None


def provider_defaults(provider: str) -> ProviderDefaults:
    return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS[DEFAULT_AI_NEWS_PROVIDER])


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider)


def provider_key_prefixes(provider: str) -> tuple[str, ...]:
    return PROVIDER_KEY_PREFIXES.get(provider, PROVIDER_KEY_PREFIXES[DEFAULT_AI_NEWS_PROVIDER])


def is_provider_metadata_field(field: str) -> bool:
    lowered = field.lower()
    return any(lowered.endswith(suffix) for suffix in PROVIDER_METADATA_SUFFIXES)


def collect_top_level_keys(
    api_keys: Mapping[str, Any],
    provider: str,
) -> list[tuple[str, str]]:
    raw_keys: list[tuple[str, str]] = []
    prefixes = provider_key_prefixes(provider)
    for field, value in api_keys.items():
        if not isinstance(field, str) or not isinstance(value, str):
            continue
        lowered = field.lower()
        if any(lowered.startswith(prefix) for prefix in prefixes):
            token = value.strip()
            if token:
                raw_keys.append((field, token))
    return raw_keys


def choose_provider(
    section: Mapping[str, Any] | None,
    api_keys: Mapping[str, Any],
) -> str:
    if section is not None:
        provider = normalize_provider(section.get("provider"))
        if provider:
            return provider

        model_candidate = (
            section.get("model") or section.get("default_model") or section.get("ai_model")
        )
        provider = infer_provider_from_model(model_candidate)
        if provider:
            return provider

        keys_section = section.get("keys")
        if isinstance(keys_section, list):
            for entry in keys_section:
                if isinstance(entry, Mapping):
                    provider = normalize_provider(entry.get("provider") or entry.get("vendor"))
                    if provider:
                        return provider

        for provider, hints in PROVIDER_SECTION_HINTS.items():
            if any(key in section for key in hints):
                return provider

    present = [
        provider
        for provider in (
            AI_NEWS_PROVIDER_ALIYUN,
            AI_NEWS_PROVIDER_GEMINI,
            AI_NEWS_PROVIDER_GLM,
        )
        if collect_top_level_keys(api_keys, provider)
    ]
    return present[0] if len(present) == 1 else DEFAULT_AI_NEWS_PROVIDER


def coerce_boolish(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return env_truthy(value)
    return default


def coerce_timeout(value: Any, default: float) -> float:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default
    return default


def normalize_provider_sequence(raw: Any) -> list[str]:
    parts: list[str] = []
    if isinstance(raw, str):
        parts.extend(item.strip() for item in raw.split(","))
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        parts.extend(str(item).strip() for item in raw)

    normalized: list[str] = []
    for item in parts:
        provider = normalize_provider(item)
        if provider and provider not in normalized:
            normalized.append(provider)
    return normalized
