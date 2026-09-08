"""Public audience configuration for delivery adapters."""

from __future__ import annotations

import os
from typing import Literal

Audience = Literal["client", "internal", "public"]

_AUDIENCE_ENV = {
    "client": "MARKET_INTEL_CLIENT_CHAT_ID",
    "internal": "MARKET_INTEL_INTERNAL_CHAT_ID",
    "public": "MARKET_INTEL_PUBLIC_CHAT_ID",
}


def _split_targets(value: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in value.replace(";", ",").split(","):
        target = raw.strip()
        if target.startswith("feishu:"):
            target = target.removeprefix("feishu:").strip()
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return tuple(result)


def resolve_audience_targets(audience: str) -> tuple[str, ...]:
    """Resolve a semantic public audience without a destination fallback."""

    try:
        env_name = _AUDIENCE_ENV[audience]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"unknown audience: {audience}") from exc
    return _split_targets(os.environ.get(env_name, ""))
