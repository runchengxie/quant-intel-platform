"""Delivery senders, preflight and orchestration helpers for A-share delivery.

Moved verbatim from ``report_delivery.py`` as a pure physical refactor.
All symbols here are re-exported from ``report_delivery`` to keep callers
and tests working unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from a_share_daily.delivery.state import _idempotency_key, _sha256_file, _write_delivery_status
from a_share_daily.delivery.targets import (
    _delivery_mode,
    _env_enabled,
    _hermes_cli_path,
    _hermes_targets,
    _lark_cli_path,
    _lark_target_arg_sets,
    _lark_targets_for_status,
)

from .notifier import FeishuWebhookNotifier, Notifier


def _run_hermes(args: Sequence[str]) -> bool:
    try:
        result = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        print(f"[report_delivery] hermes send failed: {exc}", file=sys.stderr)
        return False
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        print(
            f"[report_delivery] hermes send returned {result.returncode}: {stderr[:500]}",
            file=sys.stderr,
        )
        return False
    return True


def _run_lark(args: Sequence[str], *, cwd: Path | None = None) -> bool:
    try:
        result = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        print(f"[report_delivery] lark-cli failed: {exc}", file=sys.stderr)
        return False
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        print(
            f"[report_delivery] lark-cli returned {result.returncode}: {stderr[:500]}",
            file=sys.stderr,
        )
        return False
    return True


def _json_from_output(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _lark_bind_env() -> dict[str, str]:
    env = os.environ.copy()
    if not env.get("HERMES_HOME") and env.get("LOCALAPPDATA"):
        env["HERMES_HOME"] = str(Path(env["LOCALAPPDATA"]) / "hermes")
    return env


def _lark_whoami_ready(cli: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [cli, "whoami"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        print(f"[report_delivery] lark-cli whoami failed: {exc}", file=sys.stderr)
        return False, "whoami_exception"
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        print(
            f"[report_delivery] lark-cli whoami returned {result.returncode}: {stderr[:500]}",
            file=sys.stderr,
        )
        return False, f"whoami_returned_{result.returncode}"
    payload = _json_from_output(result.stdout or "")
    if (
        payload.get("identity") == "bot"
        and payload.get("available") is True
        and payload.get("tokenStatus") == "ready"
    ):
        return True, "ready"
    identity = str(payload.get("identity") or "unknown")
    token_status = str(payload.get("tokenStatus") or "unknown")
    available = str(payload.get("available") or "unknown").lower()
    return False, f"whoami_not_ready:{identity}:{available}:{token_status}"


def _lark_bind_from_hermes(cli: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [cli, "config", "bind", "--source", "hermes", "--identity", "bot-only"],
            env=_lark_bind_env(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        print(f"[report_delivery] lark-cli bind failed: {exc}", file=sys.stderr)
        return False, "bind_exception"
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        print(
            f"[report_delivery] lark-cli bind returned {result.returncode}: {stderr[:500]}",
            file=sys.stderr,
        )
        return False, f"bind_returned_{result.returncode}"
    return True, "bind_ok"


def _ensure_lark_ready(*, lark_cli: str | None = None, has_targets: bool = True) -> dict[str, Any]:
    """Check bot identity and re-bind Hermes credentials once when needed."""
    cli = _lark_cli_path(lark_cli)
    status: dict[str, Any] = {
        "ok": False,
        "enabled": _env_enabled("A_SHARE_LARK_PREFLIGHT", True),
        "auto_bind_enabled": _env_enabled("A_SHARE_LARK_AUTO_BIND", True),
        "bind_attempted": False,
        "bind_ok": False,
        "reason": "",
    }
    if not status["enabled"]:
        status.update({"ok": True, "reason": "preflight_disabled"})
        return status
    if not has_targets:
        status["reason"] = "no_lark_target"
        return status
    if not cli:
        status["reason"] = "lark_cli_missing"
        return status

    ready, reason = _lark_whoami_ready(cli)
    status["first_check"] = reason
    if ready:
        status.update({"ok": True, "reason": "ready"})
        return status
    if not status["auto_bind_enabled"]:
        status["reason"] = reason
        return status

    status["bind_attempted"] = True
    bind_ok, bind_reason = _lark_bind_from_hermes(cli)
    status["bind_ok"] = bind_ok
    status["bind_reason"] = bind_reason
    if not bind_ok:
        status["reason"] = bind_reason
        return status

    ready, reason = _lark_whoami_ready(cli)
    status["final_check"] = reason
    status.update({"ok": ready, "reason": "ready_after_bind" if ready else reason})
    return status


def _send_hermes_file(
    path: Path,
    *,
    subject: str,
    chat_id: str | None = None,
    target: str | None = None,
    hermes_cli: str | None = None,
) -> bool:
    cli = _hermes_cli_path(hermes_cli)
    resolved_targets = _hermes_targets(explicit=target, chat_id=chat_id)
    if not cli or not resolved_targets:
        return False
    results = []
    for resolved_target in resolved_targets:
        results.append(
            _run_hermes(
                [
                    cli,
                    "send",
                    "--to",
                    resolved_target,
                    "--subject",
                    subject,
                    "--file",
                    str(path.resolve()),
                    "--json",
                ]
            )
        )
    return all(results)


def _send_hermes_image(
    image: Path,
    *,
    chat_id: str | None = None,
    target: str | None = None,
    hermes_cli: str | None = None,
) -> bool:
    if not image.exists():
        print(f"[report_delivery] chart missing: {image}", file=sys.stderr)
        return False
    cli = _hermes_cli_path(hermes_cli)
    resolved_targets = _hermes_targets(explicit=target, chat_id=chat_id)
    if not cli or not resolved_targets:
        return False
    results = []
    for resolved_target in resolved_targets:
        results.append(
            _run_hermes(
                [
                    cli,
                    "send",
                    "--to",
                    resolved_target,
                    f"MEDIA:{image.resolve()}",
                    "--json",
                ]
            )
        )
    return all(results)


def _send_lark_markdown(
    text: str,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    lark_cli: str | None = None,
    idempotency_scope: Sequence[str] | None = None,
) -> bool:
    cli = _lark_cli_path(lark_cli)
    targets = _lark_target_arg_sets(chat_id=chat_id, user_id=user_id)
    if not cli or not targets:
        return False
    results = []
    for target in targets:
        key_material = tuple(idempotency_scope) if idempotency_scope is not None else (text,)
        idempotency_key = _idempotency_key("markdown", *target, *key_material)
        results.append(
            _run_lark(
                [
                    cli,
                    "im",
                    "+messages-send",
                    *target,
                    "--markdown",
                    text,
                    "--as",
                    "bot",
                    "--idempotency-key",
                    idempotency_key,
                    "--format",
                    "json",
                ]
            )
        )
    return all(results)


def _send_lark_image(
    image: Path,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    lark_cli: str | None = None,
) -> bool:
    if not image.exists():
        print(f"[report_delivery] chart missing: {image}", file=sys.stderr)
        return False
    cli = _lark_cli_path(lark_cli)
    targets = _lark_target_arg_sets(chat_id=chat_id, user_id=user_id)
    if not cli or not targets:
        return False
    image_hash = _sha256_file(image) or "unhashable"
    results = []
    for target in targets:
        idempotency_key = _idempotency_key("image", *target, image.name, image_hash)
        results.append(
            _run_lark(
                [
                    cli,
                    "im",
                    "+messages-send",
                    *target,
                    "--msg-type",
                    "image",
                    "--image",
                    image.name,
                    "--as",
                    "bot",
                    "--idempotency-key",
                    idempotency_key,
                    "--format",
                    "json",
                ],
                cwd=image.parent,
            )
        )
    return all(results)


def _send_webhook_text(
    path: Path, *, title: str, enabled_env: str, notifier: Notifier | None = None
) -> bool:
    if not _env_enabled(enabled_env, True):
        return False
    notifier = notifier or FeishuWebhookNotifier()
    return notifier.notify_text(title=title, path=path)


@dataclass(frozen=True)
class _DeliveryContext:
    mode: str
    chat_id: str | None
    user_id: str | None
    hermes_target: str | None
    hermes_cli: str | None
    lark_cli: str | None
    hermes_targets: list[str]
    lark_targets: list[str]


def _delivery_context(
    args: argparse.Namespace,
    *,
    chat_id_override: str | None = None,
    user_id_override: str | None = None,
    hermes_target_override: str | None = None,
) -> _DeliveryContext:
    chat_id = chat_id_override if chat_id_override is not None else getattr(args, "chat_id", None)
    user_id = user_id_override if user_id_override is not None else getattr(args, "user_id", None)
    hermes_target = (
        hermes_target_override
        if hermes_target_override is not None
        else getattr(args, "hermes_target", None)
    )
    return _DeliveryContext(
        mode=_delivery_mode(),
        chat_id=chat_id,
        user_id=user_id,
        hermes_target=hermes_target,
        hermes_cli=getattr(args, "hermes_cli", None),
        lark_cli=getattr(args, "lark_cli", None),
        hermes_targets=_hermes_targets(explicit=hermes_target, chat_id=chat_id),
        lark_targets=_lark_targets_for_status(chat_id=chat_id, user_id=user_id),
    )


def _empty_routes() -> dict[str, Any]:
    return {
        "lark_preflight": None,
        "lark_text": False,
        "lark_images": False,
        "hermes_text": False,
        "hermes_images": False,
        "webhook_text": False,
    }


def _route_enabled(kind: str, route: str, mode: str) -> bool:
    route = route.lower()
    if route == "hermes":
        allowed_modes = {"auto", "hermes", "both"}
    elif route == "lark":
        allowed_modes = {"auto", "lark", "both"}
    elif route == "webhook":
        allowed_modes = {"auto", "webhook", "both"}
    else:
        raise ValueError(f"unknown delivery route: {route}")
    return mode in allowed_modes and _env_enabled(f"{kind.upper()}_SEND_{route.upper()}", True)


def _write_disabled_delivery(
    *,
    kind: str,
    trade_date: str,
    context: _DeliveryContext,
    artifacts: Sequence[dict[str, Any]],
) -> None:
    print(f"[report_delivery] {kind} delivery disabled", file=sys.stderr)
    _write_delivery_status(
        kind=kind,
        trade_date=trade_date,
        mode=context.mode,
        success=True,
        routes={"disabled": True},
        artifacts=artifacts,
        lark_targets=context.lark_targets,
        hermes_targets=context.hermes_targets,
    )
