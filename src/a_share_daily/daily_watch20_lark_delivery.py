"""Lark send helpers for the formal DailyWatch20 presentation."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from . import daily_watch20_delivery_receipt as delivery_receipt


def send_lark_markdown(
    markdown: str,
    *,
    chat_ids: Sequence[str],
    lark_cli: str,
    dry_run: bool,
    audience: str = "client",
    attempts: list[delivery_receipt.MessageAttempt] | None = None,
) -> int:
    if dry_run:
        print(markdown)
        return 0

    failed = 0
    content_hash = hashlib.sha256(markdown.encode()).hexdigest()
    for chat_id in chat_ids:
        idempotency_key = (
            "hotsector-client-" + hashlib.sha256(f"{chat_id}\0{markdown}".encode()).hexdigest()[:24]
        )
        command = [
            lark_cli,
            "im",
            "+messages-send",
            "--chat-id",
            chat_id,
            "--markdown",
            markdown,
            "--idempotency-key",
            idempotency_key,
            "--as",
            "bot",
            "--format",
            "json",
        ]
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if attempts is not None:
            attempts.append(
                delivery_receipt.message_attempt(
                    audience=audience,
                    chat_id=chat_id,
                    medium="markdown",
                    idempotency_key=idempotency_key,
                    content_sha256=content_hash,
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
            )
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode != 0:
            failed = result.returncode
    return failed


def send_lark_image(
    image_path: Path | None,
    *,
    chat_ids: Sequence[str],
    lark_cli: str,
    dry_run: bool,
    audience: str = "client",
    attempts: list[delivery_receipt.MessageAttempt] | None = None,
) -> int:
    if image_path is None:
        return 0
    if dry_run:
        print(f"daily_watch20_png={image_path}")
        return 0
    if not image_path.is_file():
        print(f"[daily-watch20] image missing: {image_path}", file=sys.stderr)
        return 1
    image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    failed = 0
    for chat_id in chat_ids:
        key = (
            "daily-watch20-image-"
            + hashlib.sha256(f"{chat_id}\0{image_hash}".encode()).hexdigest()[:24]
        )
        command = [
            lark_cli,
            "im",
            "+messages-send",
            "--chat-id",
            chat_id,
            "--msg-type",
            "image",
            "--image",
            image_path.name,
            "--idempotency-key",
            key,
            "--as",
            "bot",
            "--format",
            "json",
        ]
        result = subprocess.run(
            command,
            cwd=image_path.parent,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if attempts is not None:
            attempts.append(
                delivery_receipt.message_attempt(
                    audience=audience,
                    chat_id=chat_id,
                    medium="image",
                    idempotency_key=key,
                    content_sha256=image_hash,
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
            )
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode != 0:
            failed = result.returncode
    return failed
