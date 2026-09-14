"""Safe, explicit personal Feishu delivery for the weekly client basket."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import datetime
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
    """Return the immutable text key for one target and ISO report week."""
    del markdown
    target_hash = hashlib.sha256(chat_id.encode()).hexdigest()[:16]
    report_week = datetime.strptime(report_date, "%Y%m%d").strftime("%G-W%V")
    return f"weekly-basket:{target_hash}:{report_week}:text"


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
            "--user-id",
            chat_id,
            "--image",
            image.name,
            "--idempotency-key",
            idempotency.removesuffix(":text") + ":image",
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

    if receipt_path.is_file():
        try:
            existing = DeliveryReceipt(**json.loads(receipt_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise WeeklyBasketDeliveryError("existing delivery receipt is invalid") from exc
        if (
            existing.report_date != report_date
            or existing.chat_id != target
            or existing.idempotency_key != key
        ):
            raise WeeklyBasketDeliveryError("existing delivery receipt identity mismatch")
        if existing.status == "sent":
            if image_path is None or existing.image_status == "sent":
                return existing
            try:
                recovered = replace(
                    existing,
                    image_status=_send_image(
                        lark_cli=lark_cli,
                        chat_id=target,
                        image_path=image_path,
                        idempotency=key,
                    ),
                )
            except (OSError, subprocess.SubprocessError):
                recovered = replace(existing, image_status="failed")
            _write_receipt(receipt_path, recovered)
            return recovered

    command = [
        lark_cli,
        "im",
        "+messages-send",
        "--as",
        "bot",
        "--user-id",
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
