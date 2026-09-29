"""Locale identifiers shared by human-facing market-intel renderers."""

from __future__ import annotations

from typing import Final

SUPPORTED_LOCALES: Final[tuple[str, ...]] = ("en-US", "zh-CN")
DEFAULT_LOCALE: Final[str] = "en-US"


def normalize_locale(value: str | None) -> str:
    """Return a supported public locale identifier or raise ``ValueError``."""

    candidate = (value or DEFAULT_LOCALE).replace("_", "-").strip()
    aliases = {
        "en": "en-US",
        "en-us": "en-US",
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "cn": "zh-CN",
    }
    normalized = aliases.get(candidate.lower(), candidate)
    if normalized not in SUPPORTED_LOCALES:
        supported = ", ".join(SUPPORTED_LOCALES)
        raise ValueError(f"Unsupported locale {value!r}; choose one of: {supported}")
    return normalized


__all__ = ["DEFAULT_LOCALE", "SUPPORTED_LOCALES", "normalize_locale"]
