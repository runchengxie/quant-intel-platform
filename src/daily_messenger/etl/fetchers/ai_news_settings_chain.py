"""Provider settings resolution for the AI market-news fetcher.

Pure physical split-out of ``ai_news.py`` (and ``ai_news_common``). Holds the
key collection, per-field provider-setting resolvers and the settings-chain
builder that turns the ``ai_news`` configuration section into a list of
``_AiNewsSettings``. These depend on the shared dataclass/helpers in
``ai_news_common``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from daily_messenger.etl.ai_news_settings import (
    choose_provider,
    coerce_boolish,
    coerce_timeout,
    collect_top_level_keys,
    infer_provider_from_model,
    is_provider_metadata_field,
    normalize_provider,
    normalize_provider_sequence,
    parse_ai_news_section,
    provider_defaults,
    provider_key_prefixes,
)
from daily_messenger.etl.ai_news_settings import (
    provider_label as _settings_provider_label,
)
from daily_messenger.etl.config import (
    AI_NEWS_PROVIDER_ALIYUN,
    AI_NEWS_PROVIDER_GEMINI,
    AI_NEWS_PROVIDER_GLM,
    DEFAULT_ALIYUN_BASE_URL,
    DEFAULT_ALIYUN_SEARCH_STRATEGY,
    DEFAULT_GLM_THINKING,
)

from .ai_news_common import _AiNewsSettings


def _collect_ai_news_keys(config: dict[str, Any], provider: str) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _push(value: Any, label: str) -> None:
        if not isinstance(value, str):
            return
        token = value.strip()
        if not token or token in seen:
            return
        keys.append((label, token))
        seen.add(token)

    raw_keys = config.get("keys")
    if isinstance(raw_keys, list):
        for idx, entry in enumerate(raw_keys, start=1):
            entry_provider = provider
            label = f"key_{idx}"
            token: Any = None
            if isinstance(entry, str):
                token = entry
            elif isinstance(entry, Mapping):
                entry_provider = str(entry.get("provider") or entry.get("vendor") or provider)
                token = entry.get("value") or entry.get("key") or entry.get("api_key")
                label = str(entry.get("label") or entry.get("name") or f"key_{idx}")
            else:
                continue
            normalized_provider = (
                normalize_provider(entry_provider) or entry_provider.strip().lower()
            )
            if normalized_provider and normalized_provider != provider:
                continue
            _push(token, label)
    else:
        single_candidate = (
            config.get("key") or config.get("api_key") or config.get("token") or config.get("value")
        )
        if isinstance(single_candidate, str):
            _push(single_candidate, "primary")

    # Allow arbitrary extra fields to serve as keys when prefixed with gemini
    relevant_prefixes = provider_key_prefixes(provider)
    for field, value in config.items():
        if not isinstance(field, str):
            continue
        lowered = field.lower()
        if not any(lowered.startswith(prefix) for prefix in relevant_prefixes):
            continue
        if is_provider_metadata_field(lowered):
            continue
        _push(value, field)

    return keys


def _first_present(section: Mapping, *keys: str) -> Any:
    for key in keys:
        value = section.get(key)
        if value not in (None, ""):
            return value
    return None


def _resolve_model(section: Mapping, provider: str) -> str:
    defaults = provider_defaults(provider)
    model_candidate = _first_present(section, defaults.model_field, "model", "default_model")
    if provider == AI_NEWS_PROVIDER_ALIYUN and infer_provider_from_model(model_candidate) in {
        AI_NEWS_PROVIDER_GLM,
        AI_NEWS_PROVIDER_GEMINI,
    }:
        model_candidate = None
    return model_candidate.strip() if isinstance(model_candidate, str) else defaults.model


def _resolve_enable_network(section: Mapping, provider: str) -> bool:
    defaults = provider_defaults(provider)
    value = _first_present(section, f"{provider}_enable_network", "enable_network")
    if value is None and provider == AI_NEWS_PROVIDER_GEMINI:
        value = section.get("google_search")
    return coerce_boolish(value, defaults.enable_network)


def _resolve_direct_connection(section: Mapping, provider: str) -> bool:
    defaults = provider_defaults(provider)
    value = _first_present(
        section,
        f"{provider}_direct_connection",
        f"{provider}_disable_proxy",
        f"{provider}_no_proxy",
        "direct_connection",
        "disable_proxy",
        "no_proxy",
    )
    return coerce_boolish(value, defaults.direct_connection)


def _resolve_timeout(section: Mapping, provider: str) -> float:
    defaults = provider_defaults(provider)
    value = _first_present(section, "timeout_seconds", "timeout", f"{provider}_timeout")
    return coerce_timeout(value, defaults.timeout)


def _resolve_extra_instructions(section: Mapping, provider: str) -> str:
    value = _first_present(
        section, f"{provider}_extra_prompt", "extra_prompt", "extra_instructions"
    )
    return value.strip() if isinstance(value, str) else ""


def _resolve_thinking(section: Mapping, provider: str) -> str | None:
    if provider != AI_NEWS_PROVIDER_GLM:
        return None
    value = _first_present(section, "thinking", "glm_thinking")
    return (
        value.strip().lower() if isinstance(value, str) and value.strip() else DEFAULT_GLM_THINKING
    )


def _resolve_aliyun_endpoint(section: Mapping, provider: str) -> tuple[str | None, str | None]:
    if provider != AI_NEWS_PROVIDER_ALIYUN:
        return None, None
    base_url = _first_present(section, "aliyun_base_url", "base_url", "dashscope_base_url")
    search_strategy = _first_present(
        section,
        "aliyun_search_strategy",
        "search_strategy",
        "dashscope_search_strategy",
    )
    return (
        base_url.strip()
        if isinstance(base_url, str) and base_url.strip()
        else DEFAULT_ALIYUN_BASE_URL,
        search_strategy.strip()
        if isinstance(search_strategy, str) and search_strategy.strip()
        else DEFAULT_ALIYUN_SEARCH_STRATEGY,
    )


def _settings_from_parts(
    *,
    provider: str,
    keys: list[tuple[str, str]],
    section: Mapping | None = None,
) -> _AiNewsSettings:
    section = section or {}
    defaults = provider_defaults(provider)
    base_url, search_strategy = _resolve_aliyun_endpoint(section, provider)
    return _AiNewsSettings(
        provider=provider,
        model=_resolve_model(section, provider) if section else defaults.model,
        keys=keys,
        enable_network=_resolve_enable_network(section, provider)
        if section
        else defaults.enable_network,
        direct_connection=_resolve_direct_connection(section, provider)
        if section
        else defaults.direct_connection,
        timeout=_resolve_timeout(section, provider) if section else defaults.timeout,
        extra_instructions=_resolve_extra_instructions(section, provider) if section else "",
        thinking=_resolve_thinking(section, provider)
        if section or provider == AI_NEWS_PROVIDER_GLM
        else None,
        base_url=base_url,
        search_strategy=search_strategy,
    )


def _resolve_ai_news_settings(api_keys: dict[str, Any]) -> _AiNewsSettings | None:
    section = parse_ai_news_section(api_keys.get("ai_news"))
    provider = choose_provider(section, api_keys)
    if section is None:
        keys = collect_top_level_keys(api_keys, provider)
        return _settings_from_parts(provider=provider, keys=keys) if keys else None

    keys = _collect_ai_news_keys(section, provider)
    if not keys:
        keys = collect_top_level_keys(api_keys, provider)
    return _settings_from_parts(provider=provider, keys=keys, section=section)


def _provider_label(provider: str) -> str:
    return _settings_provider_label(provider)


def _settings_for_provider(
    provider: str,
    primary: _AiNewsSettings | None,
    api_keys: dict[str, Any],
    section: Mapping[str, Any] | None,
) -> _AiNewsSettings | None:
    """Build the settings for a single provider by cloning ``api_keys``.

    If ``provider`` matches the already-resolved ``primary``, reuse it to avoid
    rebuilding. Otherwise clone the supplied ``section`` (overriding its
    provider) and narrow its ``keys`` list to entries belonging to this provider.
    """
    if primary and provider == primary.provider:
        return primary
    cloned = dict(api_keys)
    cloned_section = dict(section) if section is not None else {}
    cloned_section["provider"] = provider
    provider_model_field = provider_defaults(provider).model_field
    if "model" in cloned_section and provider_model_field not in cloned_section:
        cloned_section.pop("model", None)
    raw_keys = cloned_section.get("keys")
    if isinstance(raw_keys, list):
        provider_keys: list[Any] = []
        for entry in raw_keys:
            if not isinstance(entry, Mapping):
                continue
            entry_provider = entry.get("provider") or entry.get("vendor")
            if not isinstance(entry_provider, str):
                continue
            normalized = normalize_provider_sequence([entry_provider])
            if normalized and normalized[0] == provider:
                provider_keys.append(entry)
        cloned_section["keys"] = provider_keys
    cloned["ai_news"] = cloned_section
    return _resolve_ai_news_settings(cloned)


def _resolve_ai_news_settings_chain(api_keys: dict[str, Any]) -> list[_AiNewsSettings]:
    section = parse_ai_news_section(api_keys.get("ai_news"))

    raw_provider: Any = None
    raw_fallbacks: Any = None
    if section is not None:
        raw_provider = section.get("provider")
        raw_fallbacks = section.get("fallback_providers") or section.get("providers")

    provider_order = normalize_provider_sequence(raw_provider)
    provider_order.extend(
        provider
        for provider in normalize_provider_sequence(raw_fallbacks)
        if provider not in provider_order
    )

    primary = _resolve_ai_news_settings(api_keys)
    if primary and primary.provider not in provider_order:
        provider_order.insert(0, primary.provider)
    if not provider_order and primary:
        provider_order = [primary.provider]
    if not provider_order:
        return []

    for provider in (
        AI_NEWS_PROVIDER_ALIYUN,
        AI_NEWS_PROVIDER_GEMINI,
    ):
        if provider in provider_order:
            continue
        candidate = _settings_for_provider(provider, primary, api_keys, section)
        if candidate and candidate.keys:
            provider_order.append(provider)

    settings: list[_AiNewsSettings] = []
    for provider in provider_order:
        candidate = _settings_for_provider(provider, primary, api_keys, section)
        if candidate and not any(item.provider == candidate.provider for item in settings):
            settings.append(candidate)
    return settings
