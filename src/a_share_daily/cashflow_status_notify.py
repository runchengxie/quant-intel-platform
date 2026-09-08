"""Feishu status notifications for the cash-flow strategy shadow run.

This module deliberately has no target-selection input.  It is a separate
operational channel for reporting blocked, shadow, or dry-run state while the
research and PIT gates are not yet production-ready.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

STATUS_SCHEMA = "cashflow_feishu_status.v1"
ALLOWED_STATUSES = frozenset({"blocked", "shadow", "dry_run", "degraded"})
SEND_CONFIRMATION = "I_UNDERSTAND_TEST_GROUP_ONLY"


class CashflowStatusError(ValueError):
    """Raised when a status notification is unsafe or malformed."""


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _validate_status(status: dict[str, Any]) -> None:
    if status.get("status") not in ALLOWED_STATUSES:
        raise CashflowStatusError(
            f"status must be one of {sorted(ALLOWED_STATUSES)}, got {status.get('status')!r}"
        )
    for field in ("strategy_id", "policy_id", "source_date", "signal_date", "reason"):
        if not str(status.get(field, "")).strip():
            raise CashflowStatusError(f"missing status field: {field}")
    if status.get("no_target_artifact") is not True:
        raise CashflowStatusError("status notification must declare no_target_artifact=true")
    target_like_fields = {"targets", "selection", "target_weights", "symbols"}
    present = sorted(field for field in target_like_fields if field in status)
    if present:
        raise CashflowStatusError(f"target-like fields are not allowed in status payload: {present}")


def render_status_markdown(status: dict[str, Any]) -> str:
    """Render an operational-only message with no symbols or target weights."""
    _validate_status(status)
    state = str(status["status"]).upper()
    stage = str(status.get("stage") or "shadow")
    detail = str(status.get("detail") or "")
    detail_line = f"\nè¯´æï¼{detail}" if detail else ""
    return (
        "ð¡ ç°éæµç­ç¥ï½ç ç©¶ç¶æéç¥\n"
        f"ç¶æï¼{state}\n"
        f"é¶æ®µï¼{stage}\n"
        f"source_dateï¼{status['source_date']}\n"
        f"signal_dateï¼{status['signal_date']}\n"
        f"åå ï¼{status['reason']}"
        f"{detail_line}\n"
        "æ¬æ¬¡æªçæç®æ æä»ï¼ä¸æææèµå»ºè®®ã"
    )


def _identity(status: dict[str, Any]) -> dict[str, str]:
    return {
        "strategy_id": str(status["strategy_id"]),
        "policy_id": str(status["policy_id"]),
        "source_date": str(status["source_date"]),
        "signal_date": str(status["signal_date"]),
        "event_status": str(status["status"]),
        "reason": str(status["reason"]),
        "content_sha256": _sha256(status),
    }


def _idempotency_key(identity: dict[str, str], chat_id: str) -> str:
    digest = _sha256({**identity, "chat_id": chat_id})[:32]
    return f"cashflow-status-{digest}"


def _read_receipt(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CashflowStatusError(f"cannot read prior status receipt: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != STATUS_SCHEMA:
        raise CashflowStatusError("prior status receipt schema mismatch")
    return payload


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _send(
    *,
    lark_cli: str,
    chat_id: str,
    markdown: str,
    idempotency_key: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - lark-cli is an operator-configured executable
        [
            lark_cli,
            "im",
            "+messages-send",
            "--as",
            "bot",
            "--chat-id",
            chat_id,
            "--markdown",
            markdown,
            "--idempotency-key",
            idempotency_key,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise CashflowStatusError(f"lark-cli failed for {chat_id}: {result.stderr[:500]}")


def deliver_status(
    *,
    status: dict[str, Any],
    receipt_path: Path,
    chat_ids: tuple[str, ...] | list[str],
    lark_cli: str,
    dry_run: bool = True,
    send_confirmation: str | None = None,
) -> dict[str, Any]:
    """Deliver a status-only message to explicit chats, with receipt idempotency."""
    _validate_status(status)
    normalized_chat_ids = tuple(dict.fromkeys(chat_id.strip() for chat_id in chat_ids if chat_id.strip()))
    if not normalized_chat_ids:
        raise CashflowStatusError("at least one explicit Feishu chat ID is required")
    if not dry_run and send_confirmation != SEND_CONFIRMATION:
        raise CashflowStatusError(
            f"real status send requires confirmation {SEND_CONFIRMATION!r}"
        )

    identity = _identity(status)
    prior = _read_receipt(receipt_path)
    if prior is not None:
        prior_identity = {key: prior.get(key) for key in identity}
        if prior_identity != identity:
            raise CashflowStatusError("prior status receipt identity mismatch")
        prior_chats = {item.get("chat_id"): item for item in prior.get("chats", [])}
    else:
        prior_chats = {}

    markdown = render_status_markdown(status)
    chats: list[dict[str, Any]] = []
    for chat_id in normalized_chat_ids:
        key = _idempotency_key(identity, chat_id)
        previous = prior_chats.get(chat_id)
        previous_status = previous.get("status") if previous else None
        already_delivered = previous_status == "sent" or (
            dry_run and previous_status in {"dry_run", "already_sent"}
        )
        if already_delivered:
            chats.append({"chat_id": chat_id, "status": "already_sent", "idempotency_key": key})
            continue
        if dry_run:
            chat_status = "dry_run"
        else:
            _send(lark_cli=lark_cli, chat_id=chat_id, markdown=markdown, idempotency_key=key)
            chat_status = "sent"
        chats.append({"chat_id": chat_id, "status": chat_status, "idempotency_key": key})

    result = {
        "schema_version": STATUS_SCHEMA,
        **identity,
        "status": "dry_run" if dry_run else "sent",
        "success": True,
        "dry_run": dry_run,
        "no_target_artifact": True,
        "chats": chats,
    }
    _atomic_write(receipt_path, result)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send cashflow strategy status to explicit Feishu chats")
    parser.add_argument("--status-json", required=True, help="Status-only input JSON")
    parser.add_argument("--receipt", required=True, help="Status delivery receipt path")
    parser.add_argument("--chat-id", action="append", required=True, help="Explicit Feishu chat ID")
    parser.add_argument("--lark-cli", default="lark-cli")
    parser.add_argument("--send", action="store_true", help="Actually send instead of dry-run")
    parser.add_argument("--send-confirmation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        status = json.loads(Path(args.status_json).expanduser().read_text(encoding="utf-8"))
        result = deliver_status(
            status=status,
            receipt_path=Path(args.receipt).expanduser().resolve(),
            chat_ids=tuple(args.chat_id),
            lark_cli=args.lark_cli,
            dry_run=not args.send,
            send_confirmation=args.send_confirmation,
        )
    except (OSError, json.JSONDecodeError, CashflowStatusError) as exc:
        print(f"[FAIL] cashflow status notification: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

