"""Delivery-mode/env resolution and target parsing for A-share delivery.

Moved verbatim from ``report_delivery.py`` as a pure physical refactor.
All symbols here are re-exported from ``report_delivery`` to keep callers
and tests working unchanged.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from market_intel_config.audiences import resolve_audience_targets


def _delivery_mode() -> str:
    smoke_test = os.environ.get("MARKET_INTEL_SMOKE_TEST", "").strip().lower()
    smoke_send_allowed = os.environ.get("MARKET_INTEL_ALLOW_SMOKE_SEND", "").strip().lower()
    if smoke_test in {"1", "true", "yes", "on"} and smoke_send_allowed not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return "none"

    value = os.environ.get("A_SHARE_REPORT_DELIVERY", "auto").strip().lower()
    if value in {"", "auto"}:
        return "auto"
    if value in {"hermes", "hermes-send"}:
        return "hermes"
    if value in {"lark", "cli", "lark-cli"}:
        return "lark"
    if value in {"webhook", "bot"}:
        return "webhook"
    if value in {"both", "all"}:
        return "both"
    if value in {"none", "off", "0", "false"}:
        return "none"
    print(
        f"[report_delivery] unknown A_SHARE_REPORT_DELIVERY={value!r}; using auto", file=sys.stderr
    )
    return "auto"


def _env_enabled(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _lark_cli_path(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    candidate = os.environ.get("LARK_CLI") or str(Path.home() / ".local" / "bin" / "lark-cli")
    if Path(candidate).exists():
        return candidate
    return shutil.which(candidate)


def _hermes_cli_path(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    candidate = os.environ.get("HERMES_CLI") or "hermes"
    if Path(candidate).exists():
        return candidate
    return shutil.which(candidate)


def _split_targets(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _target_identity(value: str) -> str:
    value = value.strip()
    if value.startswith("feishu:"):
        value = value.removeprefix("feishu:")
    return value


def _disabled_target_ids() -> set[str]:
    values = []
    values.extend(_split_targets(os.environ.get("MARKET_INTEL_DISABLED_CHAT_ID")))
    values.extend(_split_targets(os.environ.get("MARKET_INTEL_TEST_CHAT_ID")))
    return {_target_identity(value) for value in values if _target_identity(value)}


def resolve_delivery_targets(
    *, explicit_chat_ids: Sequence[str] = (), explicit_audience: str = "client"
) -> dict[str, tuple[str, ...]]:
    """Resolve deduplicated client/internal chats while honoring disabled IDs."""

    def allowed(raw: str | Sequence[str]) -> tuple[str, ...]:
        values = _split_targets(raw) if isinstance(raw, str) else list(raw)
        disabled = _disabled_target_ids()
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            identity = _target_identity(value)
            if not identity or identity in disabled or identity in seen:
                continue
            seen.add(identity)
            result.append(identity)
        return tuple(result)

    if explicit_chat_ids:
        if explicit_audience not in {"client", "internal"}:
            raise ValueError("explicit audience must be client or internal")
        return {
            "client": allowed(explicit_chat_ids) if explicit_audience == "client" else (),
            "internal": allowed(explicit_chat_ids) if explicit_audience == "internal" else (),
        }

    client = allowed(resolve_audience_targets("client"))
    internal = allowed(resolve_audience_targets("internal"))
    client_ids = set(client)
    internal = tuple(item for item in internal if item not in client_ids)
    return {"client": client, "internal": internal}


def _split_enabled_targets(value: str | None) -> list[str]:
    disabled = _disabled_target_ids()
    targets = _split_targets(value)
    if not disabled:
        return targets
    return [target for target in targets if _target_identity(target) not in disabled]


def _legacy_chat_id() -> str:
    return _first_env("A_SHARE_FEISHU_CHAT_ID", "FEISHU_CHAT_ID")


def _audience_chat_id(audience: str) -> str:
    if audience == "weekly":
        audience = "internal"
    return ",".join(resolve_audience_targets(audience))


def _segmented_daily_targets_configured() -> bool:
    return bool(_audience_chat_id("client") or _audience_chat_id("internal"))


def _hermes_targets(
    *,
    explicit: str | None = None,
    chat_id: str | None = None,
) -> list[str]:
    target = (explicit or "").strip()
    if target:
        return [
            item if ":" in item else f"feishu:{item}" for item in _split_enabled_targets(target)
        ]

    resolved_chat = (chat_id or "").strip()
    if resolved_chat:
        return [f"feishu:{item}" for item in _split_enabled_targets(resolved_chat)]

    target = (
        os.environ.get("A_SHARE_HERMES_TARGET") or os.environ.get("HERMES_SEND_TARGET") or ""
    ).strip()
    if target:
        return [
            item if ":" in item else f"feishu:{item}" for item in _split_enabled_targets(target)
        ]

    resolved_chat = _legacy_chat_id().strip()
    if resolved_chat:
        return [f"feishu:{item}" for item in _split_enabled_targets(resolved_chat)]
    return []


def _lark_target_arg_sets(
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
) -> list[list[str]]:
    resolved_chat = (chat_id or _legacy_chat_id() or "").strip()
    resolved_user = (
        user_id
        or os.environ.get("A_SHARE_FEISHU_USER_ID")
        or os.environ.get("FEISHU_USER_ID")
        or ""
    ).strip()
    if resolved_chat:
        return [["--chat-id", item] for item in _split_enabled_targets(resolved_chat)]
    if resolved_user:
        return [["--user-id", item] for item in _split_targets(resolved_user)]
    return []


def _redact_target(value: str) -> str:
    if len(value) <= 12:
        return value
    return f"{value[:8]}...{value[-4:]}"


def _lark_targets_for_status(
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
) -> list[str]:
    targets: list[str] = []
    for args in _lark_target_arg_sets(chat_id=chat_id, user_id=user_id):
        if len(args) >= 2:
            targets.append(f"{args[0].removeprefix('--')}:{_redact_target(args[1])}")
    return targets
