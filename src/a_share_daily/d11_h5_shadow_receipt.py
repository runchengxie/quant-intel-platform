"""Read-only checks used to preserve successful D11-H5 delivery receipts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

DELIVERY_SCHEMA = "d11_h5_shadow_delivery.v1"
PRODUCT_IDS = {"d11_h5_shadow.cn.v1", "d11_h5_shadow.cn.v2"}


def successful_message(message: Any, expected_hash: str) -> bool:
    return bool(
        isinstance(message, Mapping)
        and message.get("status") in {"sent", "already_sent"}
        and message.get("content_sha256") == expected_hash
        and isinstance(message.get("message_id"), str)
        and message["message_id"]
    )


def successful_receipt_for_dates(
    receipt_path: Path,
    *,
    artifact: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return a complete successful receipt without mutating it."""

    try:
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(previous, dict):
        return None
    expected = {
        "schema_version": DELIVERY_SCHEMA,
        "source_date": artifact["source_date"],
        "signal_date": artifact["signal_date"],
        "success": True,
    }
    targets = previous.get("targets")
    if (
        any(previous.get(field) != value for field, value in expected.items())
        or previous.get("product_id") not in PRODUCT_IDS
        or not isinstance(targets, list)
        or not targets
    ):
        return None
    markdown_hash = previous.get("markdown_sha256")
    image_hash = previous.get("image_sha256")
    if not isinstance(markdown_hash, str) or not isinstance(image_hash, str):
        return None
    for target in targets:
        messages = target.get("messages") if isinstance(target, Mapping) else None
        if not isinstance(messages, Mapping) or not (
            successful_message(messages.get("markdown"), markdown_hash)
            and successful_message(messages.get("image"), image_hash)
        ):
            return None
    return cast(dict[str, Any], previous)
