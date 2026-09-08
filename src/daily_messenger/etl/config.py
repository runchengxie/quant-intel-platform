"""Runtime configuration loading for ETL jobs."""

from __future__ import annotations

import contextlib
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from daily_messenger.common.logging import log

PROJECT_ROOT = Path(__file__).resolve().parents[3]

CANONICAL_API_KEYS = (
    "alpha_vantage",
    "twelve_data",
    "financial_modeling_prep",
    "trading_economics",
    "finnhub",
    "fred",
    "sosovalue",
    "coinglass",
    "oanda",
    "alpaca_key_id",
    "alpaca_secret",
)

PREFERRED_ENV_API_KEYS: dict[str, tuple[str, ...]] = {
    "fred": ("FRED_API_KEY",),
    "oanda": ("OANDA_TOKEN", "OANDA_API_TOKEN"),
}

DEFAULT_AI_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://deepmind.com/blog/feed/basic",
]

# AI market news via GLM/Aliyun/Gemini with web search — preferred over RSS.
# Configured in api_keys.json under the "ai_news" section.
# See scripts/fetch_ai_market_news.py for the cron integration.

DEFAULT_ARXIV_PARAMS: dict[str, Any] = {
    "search_query": "cat:cs.LG OR cat:cs.AI",
    "max_results": 8,
    "sort_by": "submittedDate",
    "sort_order": "descending",
}

DEFAULT_ARXIV_THROTTLE = 3.0

AI_NEWS_PROVIDER_GLM = "glm"
AI_NEWS_PROVIDER_ALIYUN = "aliyun"
AI_NEWS_PROVIDER_GEMINI = "gemini"
DEFAULT_AI_NEWS_PROVIDER = AI_NEWS_PROVIDER_GLM

DEFAULT_GLM_MODEL = "glm-4.6"
DEFAULT_GLM_TIMEOUT = 60.0
DEFAULT_GLM_ENABLE_NETWORK = True
DEFAULT_GLM_THINKING = "enabled"
DEFAULT_GLM_DIRECT_CONNECTION = True

DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"
DEFAULT_GEMINI_TIMEOUT = 45.0
DEFAULT_GEMINI_ENABLE_NETWORK = True
DEFAULT_GEMINI_DIRECT_CONNECTION = False

DEFAULT_ALIYUN_MODEL = "qwen-plus"
DEFAULT_ALIYUN_TIMEOUT = 60.0
DEFAULT_ALIYUN_ENABLE_NETWORK = True
DEFAULT_ALIYUN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_ALIYUN_SEARCH_STRATEGY = "turbo"
DEFAULT_ALIYUN_DIRECT_CONNECTION = True


class ApiKeyValidationError(Exception):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("API key validation failed")
        self.errors = errors


def env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def coerce_api_key(value: Any) -> str | None:
    if isinstance(value, str):
        token = value.strip()
        return token or None
    if isinstance(value, dict):
        for field in ("api_key", "key", "token", "secret"):
            candidate = value.get(field)
            if isinstance(candidate, str):
                token = candidate.strip()
                if token:
                    return token
    return None


def normalize_api_keys(payload: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    normalized: dict[str, str] = {}
    extras: dict[str, Any] = {}
    canonical = set(CANONICAL_API_KEYS)
    for key, value in payload.items():
        if key in canonical:
            if value is None:
                continue
            if not isinstance(value, str):
                errors[key] = "expected string value"
                continue
            stripped = value.strip()
            if not stripped:
                errors[key] = "empty string"
                continue
            normalized[key] = stripped
        else:
            extras[key] = value
    if errors:
        raise ApiKeyValidationError(errors)
    result: dict[str, Any] = dict(normalized)
    result.update(extras)
    return result


def _candidate_api_key_paths(path_hint: str) -> list[Path]:
    expanded = Path(path_hint).expanduser()
    paths = [expanded]
    if not expanded.is_absolute():
        paths.append((PROJECT_ROOT / expanded).resolve())
    return paths


def _read_api_keys_file(path: Path, logger: logging.Logger | None) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001
        if logger:
            log(
                logger,
                logging.WARNING,
                "api_keys_path_failed",
                path=str(path),
                error=str(exc),
            )
        return None
    return dict(payload) if isinstance(payload, dict) else None


def _load_api_keys_from_path(
    logger: logging.Logger | None,
    *,
    default_path: Path | None = None,
) -> dict[str, Any]:
    path_hint = os.getenv("API_KEYS_PATH")
    candidates: list[Path]
    if path_hint:
        candidates = _candidate_api_key_paths(path_hint)
    elif default_path is not None:
        candidates = [default_path]
    else:
        candidates = [
            PROJECT_ROOT / "api_keys.json",
            Path.home() / ".config" / "market-intel" / "api_keys.json",
        ]
    for candidate in candidates:
        payload = _read_api_keys_file(candidate, logger)
        if payload is not None:
            return payload
    return {}


def _load_inline_api_keys(logger: logging.Logger | None) -> dict[str, Any]:
    raw = os.getenv("API_KEYS")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        if logger:
            log(
                logger,
                logging.ERROR,
                "api_keys_inline_invalid_json",
                error=str(exc),
            )
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _merge_canonical_env_keys(data: dict[str, Any], env: Mapping[str, str]) -> None:
    for key in CANONICAL_API_KEYS:
        if key in data:
            continue
        direct = env.get(key)
        if not direct:
            direct = env.get(key.upper())
        if direct:
            data[key] = direct


def _merge_preferred_env_api_keys(data: dict[str, Any], env: Mapping[str, str]) -> None:
    """Let established service-specific variables override JSON configuration."""

    for key, names in PREFERRED_ENV_API_KEYS.items():
        for name in names:
            value = env.get(name)
            if value and value.strip():
                data[key] = value
                break


def _merge_trading_economics_env_key(data: dict[str, Any], env: Mapping[str, str]) -> None:
    if "trading_economics" not in data:
        te_user = env.get("TRADING_ECONOMICS_USER") or env.get("trading_economics_user")
        te_password = env.get("TRADING_ECONOMICS_PASSWORD") or env.get("trading_economics_password")
        if te_user and te_password:
            data["trading_economics"] = f"{te_user}:{te_password}"


def _normalize_api_keys_with_logging(
    data: dict[str, Any],
    logger: logging.Logger | None,
) -> dict[str, Any]:
    try:
        return normalize_api_keys(data)
    except ApiKeyValidationError as exc:
        for key, reason in exc.errors.items():
            if logger:
                log(
                    logger,
                    logging.WARNING,
                    "api_key_invalid_entry",
                    key=key,
                    reason=reason,
                )
        return {
            key: value for key, value in data.items() if isinstance(value, str) and value.strip()
        }


def load_api_keys(
    logger: logging.Logger | None,
    *,
    default_path: Path | None = None,
) -> dict[str, Any]:
    data = _load_api_keys_from_path(logger, default_path=default_path)
    data.update(_load_inline_api_keys(logger))

    env = os.environ
    _merge_canonical_env_keys(data, env)
    _merge_trading_economics_env_key(data, env)
    merge_ai_news_env_config(data, env)
    _merge_preferred_env_api_keys(data, env)

    normalized = _normalize_api_keys_with_logging(data, logger)
    extra_keys = sorted(set(normalized) - set(CANONICAL_API_KEYS))
    if extra_keys and logger:
        log(logger, logging.INFO, "api_key_extra_entries", keys=extra_keys)
    return normalized


def resolve_api_key(
    key: str,
    *,
    logger: logging.Logger | None = None,
    default_path: Path | None = None,
) -> str | None:
    """Resolve one key without exposing its value to callers that do not need it.

    ``API_KEYS_PATH`` remains the explicit file selector. Callers that also support
    the conventional repository-local registry can pass that path as
    ``default_path``. Service-specific environment variables in
    ``PREFERRED_ENV_API_KEYS`` override both inline and file-backed JSON values.
    """

    return coerce_api_key(load_api_keys(logger, default_path=default_path).get(key))


def resolve_ai_feeds(config: dict[str, Any]) -> list[str]:
    feeds = config.get("ai_feeds")
    if isinstance(feeds, list):
        return [str(item).strip() for item in feeds if str(item).strip()]
    return list(DEFAULT_AI_FEEDS)


def resolve_arxiv_config(config: dict[str, Any]) -> tuple[dict[str, Any], float]:
    section = config.get("arxiv")
    params = dict(DEFAULT_ARXIV_PARAMS)
    throttle = DEFAULT_ARXIV_THROTTLE
    if isinstance(section, dict):
        search_query = section.get("search_query")
        if isinstance(search_query, str) and search_query.strip():
            params["search_query"] = search_query.strip()
        max_results = section.get("max_results")
        if isinstance(max_results, int) and max_results > 0:
            params["max_results"] = max_results
        sort_by = section.get("sort_by")
        if isinstance(sort_by, str) and sort_by.strip():
            params["sort_by"] = sort_by.strip()
        sort_order = section.get("sort_order")
        if isinstance(sort_order, str) and sort_order.strip():
            params["sort_order"] = sort_order.strip()
        throttle_val = section.get("throttle_seconds")
        if isinstance(throttle_val, (int, float)) and throttle_val >= 0:
            throttle = float(throttle_val)
    request_params = {
        "search_query": params["search_query"],
        "max_results": params["max_results"],
        "sortBy": params["sort_by"],
        "sortOrder": params["sort_order"],
    }
    return request_params, throttle


@dataclass(frozen=True)
class _AiNewsEnvKeyGroup:
    provider: str
    primary_names: tuple[str, ...]
    csv_names: tuple[str, ...]
    numbered_prefixes: tuple[str, ...]
    labeled_names: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class _AiNewsEnvField:
    target: str
    names: tuple[str, ...]
    lowercase: bool = False
    preserve_blank: bool = False


_AI_NEWS_KEY_ENV_GROUPS = (
    _AiNewsEnvKeyGroup(
        provider=AI_NEWS_PROVIDER_GEMINI,
        primary_names=("GEMINI_API_KEY", "GEMINI_KEY", "GOOGLE_GEMINI_API_KEY"),
        csv_names=("GEMINI_API_KEYS", "GEMINI_KEYS"),
        numbered_prefixes=("GEMINI_API_KEY", "GEMINI_KEY"),
        labeled_names=(
            ("GEMINI_PRIMARY_KEY", "primary"),
            ("GEMINI_BACKUP_KEY", "backup"),
            ("GEMINI_RESERVE_KEY", "reserve"),
        ),
    ),
    _AiNewsEnvKeyGroup(
        provider=AI_NEWS_PROVIDER_ALIYUN,
        primary_names=(
            "ALIYUN_API_KEY",
            "ALIYUN_BAILIAN_API_KEY",
            "BAILIAN_API_KEY",
            "DASHSCOPE_API_KEY",
            "QWEN_API_KEY",
        ),
        csv_names=("ALIYUN_API_KEYS", "BAILIAN_API_KEYS", "DASHSCOPE_API_KEYS", "QWEN_API_KEYS"),
        numbered_prefixes=(
            "ALIYUN_API_KEY",
            "BAILIAN_API_KEY",
            "DASHSCOPE_API_KEY",
            "QWEN_API_KEY",
        ),
    ),
    _AiNewsEnvKeyGroup(
        provider=AI_NEWS_PROVIDER_GLM,
        primary_names=(
            "GLM_API_KEY",
            "GLM_KEY",
            "ZHIPUAI_API_KEY",
            "ZHIPU_API_KEY",
            "ZAI_API_KEY",
        ),
        csv_names=("GLM_API_KEYS", "GLM_KEYS", "ZHIPU_API_KEYS", "ZHIPUAI_KEYS"),
        numbered_prefixes=("GLM_API_KEY", "GLM_KEY", "ZHIPUAI_API_KEY", "ZHIPU_API_KEY"),
    ),
)

_AI_NEWS_STRING_ENV_FIELDS = (
    _AiNewsEnvField("provider", ("AI_NEWS_PROVIDER",), lowercase=True),
    _AiNewsEnvField("model", ("AI_NEWS_MODEL",)),
    _AiNewsEnvField("glm_model", ("GLM_MODEL", "ZHIPU_MODEL", "ZHIPUAI_MODEL")),
    _AiNewsEnvField("gemini_model", ("GEMINI_MODEL", "GEMINI_DEFAULT_MODEL")),
    _AiNewsEnvField(
        "aliyun_model",
        ("ALIYUN_MODEL", "BAILIAN_MODEL", "DASHSCOPE_MODEL", "QWEN_MODEL"),
    ),
    _AiNewsEnvField("extra_prompt", ("AI_NEWS_EXTRA_PROMPT",)),
    _AiNewsEnvField("glm_extra_prompt", ("GLM_EXTRA_PROMPT",)),
    _AiNewsEnvField("gemini_extra_prompt", ("GEMINI_EXTRA_PROMPT",)),
    _AiNewsEnvField("aliyun_extra_prompt", ("ALIYUN_EXTRA_PROMPT", "BAILIAN_EXTRA_PROMPT")),
    _AiNewsEnvField(
        "aliyun_base_url", ("ALIYUN_BASE_URL", "BAILIAN_BASE_URL", "DASHSCOPE_BASE_URL")
    ),
    _AiNewsEnvField(
        "aliyun_search_strategy",
        ("ALIYUN_SEARCH_STRATEGY", "BAILIAN_SEARCH_STRATEGY", "DASHSCOPE_SEARCH_STRATEGY"),
    ),
    _AiNewsEnvField("thinking", ("AI_NEWS_THINKING",)),
    _AiNewsEnvField("glm_thinking", ("GLM_THINKING",)),
)

_AI_NEWS_BOOL_ENV_FIELDS = (
    _AiNewsEnvField("enable_network", ("AI_NEWS_ENABLE_NETWORK",), preserve_blank=True),
    _AiNewsEnvField("glm_enable_network", ("GLM_ENABLE_NETWORK", "ZHIPU_ENABLE_NETWORK")),
    _AiNewsEnvField("gemini_enable_network", ("GEMINI_ENABLE_NETWORK", "GEMINI_GOOGLE_SEARCH")),
    _AiNewsEnvField("aliyun_enable_network", ("ALIYUN_ENABLE_NETWORK", "BAILIAN_ENABLE_NETWORK")),
    _AiNewsEnvField(
        "direct_connection",
        (
            "AI_NEWS_DIRECT_CONNECTION",
            "AI_NEWS_DIRECT",
            "AI_NEWS_DISABLE_PROXY",
            "AI_NEWS_NO_PROXY",
        ),
        preserve_blank=True,
    ),
    _AiNewsEnvField(
        "glm_direct_connection",
        (
            "GLM_DIRECT_CONNECTION",
            "ZHIPU_DIRECT_CONNECTION",
            "ZHIPUAI_DIRECT_CONNECTION",
            "GLM_DISABLE_PROXY",
            "ZHIPU_DISABLE_PROXY",
            "ZHIPUAI_DISABLE_PROXY",
        ),
        preserve_blank=True,
    ),
    _AiNewsEnvField(
        "gemini_direct_connection",
        (
            "GEMINI_DIRECT_CONNECTION",
            "GOOGLE_GEMINI_DIRECT_CONNECTION",
            "GEMINI_DISABLE_PROXY",
        ),
        preserve_blank=True,
    ),
    _AiNewsEnvField(
        "aliyun_direct_connection",
        (
            "ALIYUN_DIRECT_CONNECTION",
            "BAILIAN_DIRECT_CONNECTION",
            "DASHSCOPE_DIRECT_CONNECTION",
            "QWEN_DIRECT_CONNECTION",
            "ALIYUN_DISABLE_PROXY",
            "BAILIAN_DISABLE_PROXY",
            "DASHSCOPE_DISABLE_PROXY",
            "QWEN_DISABLE_PROXY",
        ),
        preserve_blank=True,
    ),
)


def _coerce_env_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _first_env(
    env: Mapping[str, str],
    names: tuple[str, ...],
    *,
    preserve_blank: bool = False,
) -> str | None:
    for name in names:
        if name not in env:
            continue
        raw = env.get(name)
        if preserve_blank:
            return raw
        token = _coerce_env_str(raw)
        if token is not None:
            return token
    return None


def _collect_ai_news_env_key_candidates(env: Mapping[str, str]) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []

    def add(raw: str | None, label: str, provider: str) -> None:
        token = _coerce_env_str(raw if isinstance(raw, str) else None)
        if token:
            candidates.append((provider, label, token))

    for group in _AI_NEWS_KEY_ENV_GROUPS:
        for name in group.primary_names:
            add(env.get(name), "env_primary", group.provider)

        csv_payload = _first_env(env, group.csv_names)
        if csv_payload:
            for idx, segment in enumerate(csv_payload.split(","), start=1):
                add(segment, f"env_{idx}", group.provider)

        for idx in range(1, 11):
            for prefix in group.numbered_prefixes:
                add(env.get(f"{prefix}_{idx}"), f"env_{idx}", group.provider)

        for name, label in group.labeled_names:
            add(env.get(name), label, group.provider)

    return candidates


def _extract_ai_news_key_entry(
    entry: Any,
    section_provider: Any,
) -> tuple[str | None, str | None]:
    if isinstance(entry, str):
        return _coerce_env_str(entry), section_provider if isinstance(
            section_provider, str
        ) else None
    if isinstance(entry, Mapping):
        value = entry.get("value") or entry.get("key") or entry.get("api_key")
        provider = entry.get("provider") or entry.get("vendor")
        if isinstance(value, str):
            return _coerce_env_str(value), (
                str(provider).strip().lower() if isinstance(provider, str) else None
            )
    return None, None


def _merge_ai_news_env_keys(
    section: dict[str, Any],
    env_candidates: list[tuple[str, str, str]],
) -> None:
    if not env_candidates:
        return

    existing_keys_raw = section.get("keys")
    combined: list[Any] = list(existing_keys_raw) if isinstance(existing_keys_raw, list) else []
    seen_pairs: set[tuple[str, str]] = set()
    seen_tokens: set[str] = set()
    provider_hint = section.get("provider")
    default_provider = provider_hint.strip().lower() if isinstance(provider_hint, str) else None

    for item in combined:
        token, provider_override = _extract_ai_news_key_entry(item, section.get("provider"))
        if not token:
            continue
        provider_value = provider_override or default_provider or ""
        seen_pairs.add((provider_value, token))
        seen_tokens.add(token)

    for provider, label, token in env_candidates:
        if token in seen_tokens or (provider, token) in seen_pairs:
            continue
        combined.append({"value": token, "label": label, "provider": provider})
        seen_pairs.add((provider, token))
        seen_tokens.add(token)
    section["keys"] = combined


def _apply_ai_news_string_env_fields(section: dict[str, Any], env: Mapping[str, str]) -> None:
    for field in _AI_NEWS_STRING_ENV_FIELDS:
        value = _first_env(env, field.names)
        if value is None:
            continue
        section[field.target] = value.lower() if field.lowercase else value


def _apply_ai_news_fallback_env(section: dict[str, Any], env: Mapping[str, str]) -> None:
    fallback_providers = _first_env(env, ("AI_NEWS_FALLBACK_PROVIDERS",))
    if fallback_providers:
        section["fallback_providers"] = [
            item.strip().lower() for item in fallback_providers.split(",") if item.strip()
        ]


def _apply_ai_news_bool_env_fields(section: dict[str, Any], env: Mapping[str, str]) -> None:
    for field in _AI_NEWS_BOOL_ENV_FIELDS:
        value = _first_env(env, field.names, preserve_blank=field.preserve_blank)
        if value is not None:
            section[field.target] = env_truthy(str(value))


def _apply_ai_news_timeout_env(section: dict[str, Any], env: Mapping[str, str]) -> None:
    timeout_fields = (
        _AiNewsEnvField("timeout", ("AI_NEWS_TIMEOUT",)),
        _AiNewsEnvField("glm_timeout", ("GLM_TIMEOUT", "ZHIPU_TIMEOUT", "ZHIPUAI_TIMEOUT")),
        _AiNewsEnvField("gemini_timeout", ("GEMINI_TIMEOUT", "GOOGLE_GEMINI_TIMEOUT")),
        _AiNewsEnvField(
            "aliyun_timeout", ("ALIYUN_TIMEOUT", "BAILIAN_TIMEOUT", "DASHSCOPE_TIMEOUT")
        ),
    )
    for field in timeout_fields:
        timeout_env = _first_env(env, field.names)
        if timeout_env:
            with contextlib.suppress(ValueError):
                parsed = float(timeout_env)
                if parsed > 0:
                    section[field.target] = parsed


def merge_ai_news_env_config(data: dict[str, Any], env: Mapping[str, str]) -> None:
    existing_section = data.get("ai_news")
    section: dict[str, Any] = dict(existing_section) if isinstance(existing_section, dict) else {}

    _merge_ai_news_env_keys(section, _collect_ai_news_env_key_candidates(env))
    _apply_ai_news_string_env_fields(section, env)
    _apply_ai_news_fallback_env(section, env)
    _apply_ai_news_bool_env_fields(section, env)
    _apply_ai_news_timeout_env(section, env)

    if section:
        data["ai_news"] = section


def load_configuration(
    logger: logging.Logger | None = None,
) -> tuple[dict[str, Any], list[str], dict[str, Any], float]:
    api_keys = load_api_keys(logger)
    ai_feeds = resolve_ai_feeds(api_keys)
    arxiv_params, arxiv_throttle = resolve_arxiv_config(api_keys)
    return api_keys, ai_feeds, arxiv_params, arxiv_throttle
