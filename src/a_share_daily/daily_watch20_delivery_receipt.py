"""Durable, content-addressed delivery receipts for DailyWatch20."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DELIVERY_SCHEMA = "daily_watch20_delivery.v1"
PRODUCT_ID = "daily_watch20.cn.v1"
SUCCESSFUL_MESSAGE_STATUSES = frozenset({"already_sent", "sent"})


@dataclass(frozen=True, slots=True)
class DeliveryPresentation:
    audience: str
    markdown_path: str
    markdown_sha256: str
    image_path: str
    image_sha256: str
    html_path: str | None
    html_sha256: str | None


@dataclass(frozen=True, slots=True)
class MessageAttempt:
    audience: str
    target_sha256: str
    medium: str
    status: str
    idempotency_key: str
    content_sha256: str
    message_id: str | None
    attempted_at: str
    error: str | None


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_fingerprint(chat_id: str) -> str:
    identity = chat_id.removeprefix("feishu:").strip()
    return sha256_bytes(f"lark-chat\0{identity}".encode())


def _json_from_output(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _message_id(payload: Mapping[str, Any]) -> str | None:
    data = payload.get("data")
    candidates: list[Any] = [payload.get("message_id"), payload.get("messageId")]
    if isinstance(data, Mapping):
        candidates.extend((data.get("message_id"), data.get("messageId")))
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def message_attempt(
    *,
    audience: str,
    chat_id: str,
    medium: str,
    idempotency_key: str,
    content_sha256: str,
    returncode: int,
    stdout: str,
    stderr: str,
) -> MessageAttempt:
    payload = _json_from_output(stdout or stderr)
    message_id = _message_id(payload)
    confirmed = returncode == 0 and payload.get("ok") is not False and bool(message_id)
    diagnostic = " ".join((stderr or stdout or "message id missing").split())[:300]
    return MessageAttempt(
        audience=audience,
        target_sha256=target_fingerprint(chat_id),
        medium=medium,
        status="sent" if confirmed else "failed",
        idempotency_key=idempotency_key,
        content_sha256=content_sha256,
        message_id=message_id,
        attempted_at=datetime.now(UTC).isoformat(),
        error=None if confirmed else diagnostic,
    )


def presentation(
    *,
    audience: str,
    markdown: str,
    markdown_path: Path,
    image_path: Path,
    html_path: Path | None,
) -> DeliveryPresentation:
    markdown_hash = sha256_bytes(markdown.encode())
    if sha256_file(markdown_path) != markdown_hash:
        raise ValueError("rendered DailyWatch20 Markdown does not match delivery text")
    return DeliveryPresentation(
        audience=audience,
        markdown_path=str(markdown_path.resolve()),
        markdown_sha256=markdown_hash,
        image_path=str(image_path.resolve()),
        image_sha256=sha256_file(image_path),
        html_path=str(html_path.resolve()) if html_path else None,
        html_sha256=sha256_file(html_path) if html_path else None,
    )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _snapshot_source_receipt(source: Path, delivery_path: Path) -> Path:
    source_bytes = source.read_bytes()
    snapshot = delivery_path.with_name("source_selection_receipt.json")
    if snapshot.is_file():
        if snapshot.read_bytes() != source_bytes:
            raise ValueError("DailyWatch20 source receipt snapshot lineage changed")
        return snapshot
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    temporary = snapshot.with_name(f".{snapshot.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(source_bytes)
        temporary.replace(snapshot)
    finally:
        temporary.unlink(missing_ok=True)
    return snapshot


def write_delivery_receipt(
    *,
    path: Path,
    source_date: str,
    signal_date: str,
    source_receipt_path: Path,
    presentations: Sequence[DeliveryPresentation],
    attempts: Sequence[MessageAttempt],
) -> dict[str, Any]:
    """Write one atomic receipt after all audience sends have been attempted."""

    source_receipt_snapshot = _snapshot_source_receipt(source_receipt_path, path)
    presentation_map = {item.audience: asdict(item) for item in presentations}
    targets: list[dict[str, Any]] = []
    target_index: dict[tuple[str, str], dict[str, Any]] = {}
    for attempt in attempts:
        key = (attempt.audience, attempt.target_sha256)
        target: dict[str, Any] | None = target_index.get(key)
        if target is None:
            target = {
                "audience": attempt.audience,
                "target_sha256": attempt.target_sha256,
                "messages": {},
            }
            target_index[key] = target
            targets.append(target)
        messages = target["messages"]
        if not isinstance(messages, dict):
            raise ValueError("DailyWatch20 target messages must be a dict")
        messages[attempt.medium] = {
            key: value
            for key, value in asdict(attempt).items()
            if key not in {"audience", "target_sha256", "medium"}
        }

    required_audiences = sorted(presentation_map)
    success = bool(targets) and all(
        isinstance(target.get("messages"), Mapping)
        and all(
            isinstance(target["messages"].get(medium), Mapping)
            and target["messages"][medium].get("status") in SUCCESSFUL_MESSAGE_STATUSES
            for medium in ("markdown", "image")
        )
        for target in targets
    )
    delivered_audiences = {
        str(target["audience"])
        for target in targets
        if all(
            target["messages"].get(medium, {}).get("status") in SUCCESSFUL_MESSAGE_STATUSES
            for medium in ("markdown", "image")
        )
    }
    success = success and set(required_audiences) <= delivered_audiences
    now = datetime.now(UTC).isoformat()
    receipt: dict[str, Any] = {
        "schema_version": DELIVERY_SCHEMA,
        "product_id": PRODUCT_ID,
        "source_date": source_date,
        "signal_date": signal_date,
        "source_receipt_origin": str(source_receipt_path.resolve()),
        "source_receipt_path": str(source_receipt_snapshot.resolve()),
        "source_receipt_sha256": sha256_file(source_receipt_snapshot),
        "presentations": presentation_map,
        "created_at": now,
        "updated_at": now,
        "success": success,
        "targets": targets,
    }
    _atomic_write_json(path, receipt)
    return receipt


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{label} 无法读取：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是 JSON object")
    return value


def _validate_presentation(audience: str, value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return [f"投递回执缺少 {audience} presentation"]
    problems: list[str] = []
    for medium in ("markdown", "image", "html"):
        path_value = value.get(f"{medium}_path")
        expected_hash = value.get(f"{medium}_sha256")
        if path_value is None and medium == "html":
            continue
        if not isinstance(path_value, str) or not path_value:
            problems.append(f"{audience} {medium} 路径无效")
            continue
        path = Path(path_value)
        if not path.is_file():
            problems.append(f"{audience} {medium} 产物缺失：{path}")
        elif not isinstance(expected_hash, str) or sha256_file(path) != expected_hash:
            problems.append(f"{audience} {medium} 产物 hash 不一致")
    return problems


def _validate_expected_fields(
    receipt: Mapping[str, object],
    *,
    expected_source_date: str,
    expected_signal_date: str,
) -> list[str]:
    problems: list[str] = []
    expected_fields: dict[str, object] = {
        "schema_version": DELIVERY_SCHEMA,
        "product_id": PRODUCT_ID,
        "source_date": expected_source_date,
        "signal_date": expected_signal_date,
        "success": True,
    }
    for field, expected in expected_fields.items():
        if receipt.get(field) != expected:
            problems.append(
                f"DailyWatch20 delivery receipt {field}={receipt.get(field)!r}，期望 {expected!r}"
            )
    return problems


def _validate_source_receipt(receipt: Mapping[str, object]) -> list[str]:
    problems: list[str] = []
    source_receipt_value = receipt.get("source_receipt_path")
    source_receipt_hash = receipt.get("source_receipt_sha256")
    if not isinstance(source_receipt_value, str) or not source_receipt_value:
        problems.append("DailyWatch20 source receipt 路径缺失")
        return problems
    source_receipt = Path(source_receipt_value)
    if not source_receipt.is_file():
        problems.append(f"DailyWatch20 source receipt 缺失：{source_receipt}")
    elif (
        not isinstance(source_receipt_hash, str)
        or sha256_file(source_receipt) != source_receipt_hash
    ):
        problems.append("DailyWatch20 source receipt hash 不一致")
    return problems


def _is_target_complete(target: object, presentation_value: object) -> bool:
    if not isinstance(target, Mapping):
        return False
    if not isinstance(presentation_value, Mapping):
        return False
    messages = target.get("messages")
    if not isinstance(messages, Mapping):
        return False
    for medium in ("markdown", "image"):
        message = messages.get(medium)
        expected_hash = presentation_value.get(f"{medium}_sha256")
        if (
            not isinstance(message, Mapping)
            or message.get("status") not in SUCCESSFUL_MESSAGE_STATUSES
            or message.get("content_sha256") != expected_hash
            or not isinstance(message.get("message_id"), str)
            or not message.get("message_id")
        ):
            return False
    return True


def _validate_targets(
    targets: object,
    presentations: Mapping[str, object],
    required_audiences: Sequence[str],
) -> list[str]:
    if not isinstance(targets, list):
        return ["DailyWatch20 delivery targets 不是列表"]
    problems: list[str] = []
    completed_audiences: set[str] = set()
    for target in targets:
        if not isinstance(target, Mapping):
            problems.append("DailyWatch20 delivery receipt 含无效 target")
            continue
        audience = target.get("audience")
        if not isinstance(audience, str):
            continue
        if _is_target_complete(target, presentations.get(audience)):
            completed_audiences.add(audience)
    missing = sorted(set(required_audiences) - completed_audiences)
    if missing:
        problems.append("DailyWatch20 缺少完整投递 audience：" + ",".join(missing))
    return problems


def validate_delivery_receipt(
    *,
    path: Path,
    expected_source_date: str,
    expected_signal_date: str,
    required_audiences: Sequence[str],
) -> list[str]:
    if not path.is_file():
        return [f"当日 DailyWatch20 delivery receipt 缺失：{path}"]
    try:
        receipt = _read_json_object(path, "DailyWatch20 delivery receipt")
    except ValueError as exc:
        return [str(exc)]
    problems: list[str] = []

    problems.extend(
        _validate_expected_fields(
            receipt,
            expected_source_date=expected_source_date,
            expected_signal_date=expected_signal_date,
        )
    )
    problems.extend(_validate_source_receipt(receipt))

    presentations = receipt.get("presentations")
    if not isinstance(presentations, Mapping):
        problems.append("DailyWatch20 delivery presentations 不是 object")
        presentations = {}
    for audience in required_audiences:
        problems.extend(_validate_presentation(audience, presentations.get(audience)))

    problems.extend(_validate_targets(receipt.get("targets"), presentations, required_audiences))
    return problems
