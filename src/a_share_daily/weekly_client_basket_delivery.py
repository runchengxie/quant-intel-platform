"""Safe, explicit personal Feishu delivery for the weekly client basket."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .weekly_client_basket import _atomic_write


class WeeklyBasketDeliveryError(ValueError):
    """Raised when a weekly basket delivery target is unsafe."""


@dataclass(frozen=True)
class DeliveryReceipt:
    status: str
    report_date: str
    chat_id: str
    idempotency_key: str
    markdown_sha256: str
    identity: str = "app"
    returncode: int | None = None
    stderr: str = ""
    image_status: str = "not_requested"


def personal_chat_id(explicit_chat_id: str | None = None) -> str:
    """Return only the dedicated personal target; never reuse group settings."""
    value = (explicit_chat_id or os.environ.get("WEEKLY_BASKET_PERSONAL_CHAT_ID") or "").strip()
    if not value:
        raise WeeklyBasketDeliveryError(
            "personal Feishu chat ID is required via --personal-chat-id or "
            "WEEKLY_BASKET_PERSONAL_CHAT_ID"
        )
    if any(separator in value for separator in (",", ";", "\n", "\r")):
        raise WeeklyBasketDeliveryError("personal delivery requires a single chat ID")
    if value.startswith("oc_"):
        raise WeeklyBasketDeliveryError("personal delivery rejects group chat IDs")
    return value


def idempotency_key(chat_id: str, report_date: str, markdown: str) -> str:
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:24]
    scope = hashlib.sha256(f"{chat_id}:{report_date}:{digest}".encode()).hexdigest()[:24]
    return f"weekly-basket-text-{scope}"


def _write_receipt(path: Path, receipt: DeliveryReceipt) -> None:
    _atomic_write(
        path,
        (json.dumps(asdict(receipt), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def _send_image(*, lark_cli: str, chat_id: str, image_path: Path, idempotency: str) -> str:
    image = image_path.expanduser().resolve()
    result = subprocess.run(  # noqa: S603
        [
            lark_cli,
            "im",
            "+messages-send",
            "--as",
            "bot",
            "--chat-id",
            chat_id,
            "--image",
            image.name,
            "--idempotency-key",
            f"{idempotency}-image",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=image.parent,
    )
    return "sent" if result.returncode == 0 else "failed"


def send_personal_basket_report(
    markdown: str,
    *,
    report_date: str,
    chat_id: str,
    lark_cli: str,
    receipt_path: Path,
    dry_run: bool = False,
    image_path: Path | None = None,
) -> DeliveryReceipt:
    """Send once to one explicit personal chat using the app identity."""
    target = personal_chat_id(chat_id)
    key = idempotency_key(target, report_date, markdown)
    markdown_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    if dry_run:
        receipt = DeliveryReceipt(
            status="dry_run",
            report_date=report_date,
            chat_id=target,
            idempotency_key=key,
            markdown_sha256=markdown_hash,
            image_status="dry_run" if image_path else "not_requested",
        )
        _write_receipt(receipt_path, receipt)
        return receipt

    command = [
        lark_cli,
        "im",
        "+messages-send",
        "--as",
        "bot",
        "--chat-id",
        target,
        "--markdown",
        markdown,
        "--idempotency-key",
        key,
        "--format",
        "json",
    ]
    try:
        result = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        status = "sent" if result.returncode == 0 else "failed"
        receipt = DeliveryReceipt(
            status=status,
            report_date=report_date,
            chat_id=target,
            idempotency_key=key,
            markdown_sha256=markdown_hash,
            returncode=result.returncode,
            stderr=result.stderr[-500:],
        )
        if receipt.status == "sent" and image_path is not None:
            try:
                receipt = replace(
                    receipt,
                    image_status=_send_image(
                        lark_cli=lark_cli, chat_id=target, image_path=image_path, idempotency=key
                    ),
                )
            except (OSError, subprocess.SubprocessError):
                receipt = replace(receipt, image_status="failed")
    except (OSError, subprocess.SubprocessError) as exc:
        receipt = DeliveryReceipt(
            status="failed",
            report_date=report_date,
            chat_id=target,
            idempotency_key=key,
            markdown_sha256=markdown_hash,
            stderr=str(exc),
        )
    _write_receipt(receipt_path, receipt)
    return receipt


__all__ = [
    "DeliveryReceipt",
    "WeeklyBasketDeliveryError",
    "idempotency_key",
    "personal_chat_id",
    "send_personal_basket_report",
]
