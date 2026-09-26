"""Delivery route implementations shared by morning and evening reports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from a_share_daily.delivery import senders, state
from a_share_daily.delivery._format import _read_text


@dataclass(frozen=True)
class MorningDeliveryContext:
    context: senders._DeliveryContext
    trade_date: str
    signal_date: str
    mode: str
    text: str
    report_path: Path
    chart_paths: Sequence[Path]
    artifacts: Sequence[dict[str, Any]]
    routes_payload: dict[str, Any]
    message_ids: dict[str, list[str]]


def write_morning_delivery_status(
    delivery: MorningDeliveryContext,
    *,
    success: bool,
) -> dict[str, Any]:
    """Persist the morning receipt with its signal, artifact, route, and message data."""
    context = delivery.context
    return state._write_delivery_status(
        kind="morning",
        trade_date=delivery.trade_date,
        signal_date=delivery.signal_date,
        mode=delivery.mode,
        success=success,
        routes=delivery.routes_payload,
        artifacts=delivery.artifacts,
        lark_targets=context.lark_targets,
        hermes_targets=context.hermes_targets,
        message_ids=delivery.message_ids,
    )


def deliver_morning_via_lark(
    delivery: MorningDeliveryContext,
) -> tuple[bool, bool]:
    """Send the morning report and charts through Lark, recording route state."""
    context = delivery.context
    preflight = senders._ensure_lark_ready(
        lark_cli=context.lark_cli, has_targets=bool(context.lark_targets)
    )
    delivery.routes_payload["lark_preflight"] = preflight
    if not preflight.get("ok"):
        delivery.routes_payload["lark_text"] = False
        delivery.routes_payload["lark_images"] = False
        return (False, False)

    text_ok = senders._send_lark_markdown(
        delivery.text,
        chat_id=context.chat_id,
        user_id=context.user_id,
        lark_cli=context.lark_cli,
        message_ids=delivery.message_ids.setdefault("lark_text", []),
        idempotency_scope=("morning", delivery.trade_date, "morning_report"),
    )
    image_results = [
        senders._send_lark_image(
            image,
            chat_id=context.chat_id,
            user_id=context.user_id,
            lark_cli=context.lark_cli,
            message_ids=delivery.message_ids.setdefault("lark_images", []),
        )
        for image in delivery.chart_paths
    ]
    images_ok = all(image_results) if image_results else True
    delivery.routes_payload["lark_text"] = text_ok
    delivery.routes_payload["lark_images"] = images_ok
    return (text_ok, images_ok)


def deliver_morning_via_hermes(
    delivery: MorningDeliveryContext,
) -> tuple[bool, bool]:
    """Send the morning report and charts through Hermes."""
    context = delivery.context
    text_ok = senders._send_hermes_file(
        delivery.report_path,
        subject="亚洲市场盘前 / 美股市场盘后",
        chat_id=context.chat_id,
        target=context.hermes_target,
        hermes_cli=context.hermes_cli,
    )
    image_results = [
        senders._send_hermes_image(
            image,
            chat_id=context.chat_id,
            target=context.hermes_target,
            hermes_cli=context.hermes_cli,
        )
        for image in delivery.chart_paths
    ]
    images_ok = all(image_results) if image_results else True
    delivery.routes_payload["hermes_text"] = text_ok
    delivery.routes_payload["hermes_images"] = images_ok
    return (text_ok, images_ok)


def deliver_via_lark(
    *,
    context: senders._DeliveryContext,
    kind: str,
    trade_date: str,
    text_files: Sequence[tuple[Path, str, str]],
    image_paths: Sequence[Path],
    routes_payload: dict[str, Any],
    mode: str,
    message_ids: dict[str, list[str]] | None = None,
) -> tuple[bool, bool]:
    lark_preflight = senders._ensure_lark_ready(
        lark_cli=context.lark_cli, has_targets=bool(context.lark_targets)
    )
    routes_payload["lark_preflight"] = lark_preflight
    if not lark_preflight.get("ok"):
        return (False, False)
    lark_text_results = [
        senders._send_lark_markdown(
            _read_text(path),
            chat_id=context.chat_id,
            user_id=context.user_id,
            lark_cli=context.lark_cli,
            idempotency_scope=(kind, trade_date, path.name),
            message_ids=(
                message_ids.setdefault("lark_text", []) if message_ids is not None else None
            ),
        )
        for path, _subject, _title in text_files
    ]
    lark_text_ok = all(lark_text_results) if lark_text_results else True
    lark_image_results = [
        senders._send_lark_image(
            image,
            chat_id=context.chat_id,
            user_id=context.user_id,
            lark_cli=context.lark_cli,
            message_ids=(
                message_ids.setdefault("lark_images", []) if message_ids is not None else None
            ),
        )
        for image in image_paths
    ]
    lark_images_ok = all(lark_image_results) if lark_image_results else True
    routes_payload["lark_text"] = lark_text_ok
    routes_payload["lark_images"] = lark_images_ok
    return (lark_text_ok, lark_images_ok)


def deliver_via_hermes(
    *,
    context: senders._DeliveryContext,
    kind: str,
    trade_date: str,
    text_files: Sequence[tuple[Path, str, str]],
    image_paths: Sequence[Path],
    routes_payload: dict[str, Any],
    mode: str,
    lark_text_ok: bool,
    lark_images_ok: bool,
) -> tuple[bool, bool]:
    if mode != "both" and lark_text_ok:
        hermes_text_ok = True
    else:
        hermes_text_results = [
            senders._send_hermes_file(
                path,
                subject=subject,
                chat_id=context.chat_id,
                target=context.hermes_target,
                hermes_cli=context.hermes_cli,
            )
            for path, subject, _title in text_files
        ]
        hermes_text_ok = all(hermes_text_results) if hermes_text_results else True
    if mode != "both" and lark_images_ok:
        hermes_images_ok = True
    else:
        hermes_image_results = [
            senders._send_hermes_image(
                image,
                chat_id=context.chat_id,
                target=context.hermes_target,
                hermes_cli=context.hermes_cli,
            )
            for image in image_paths
        ]
        hermes_images_ok = all(hermes_image_results) if hermes_image_results else True
    routes_payload["hermes_text"] = hermes_text_ok
    routes_payload["hermes_images"] = hermes_images_ok
    if mode == "hermes" and not (hermes_text_ok and hermes_images_ok):
        state._write_delivery_status(
            kind=kind,
            trade_date=trade_date,
            mode=mode,
            success=False,
            routes=routes_payload,
            artifacts=[],
            lark_targets=context.lark_targets,
            hermes_targets=context.hermes_targets,
        )
        return (False, False)
    return (hermes_text_ok, hermes_images_ok)


def deliver_via_webhook(
    *,
    text_files: Sequence[tuple[Path, str, str]],
    routes_payload: dict[str, Any],
    webhook_enabled_env: str,
) -> bool:
    webhook_results = [
        senders._send_webhook_text(path, title=title, enabled_env=webhook_enabled_env)
        for path, _subject, title in text_files
    ]
    webhook_ok = all(webhook_results) if webhook_results else True
    routes_payload["webhook_text"] = webhook_ok
    return webhook_ok
