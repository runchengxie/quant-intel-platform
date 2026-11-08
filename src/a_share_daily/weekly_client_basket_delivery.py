"""Week-scoped, durable and fail-closed weekly basket delivery."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .weekly_basket_delivery_store import durable_write, exclusive_lock, sha256_file

SCHEMA = "weekly_basket.delivery.v2"


class WeeklyBasketDeliveryError(ValueError):
    """An unsafe or unverifiable basket delivery request."""


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
    verification_level: str = "unverified"
    text_state: str = "not_started"
    image_state: str = "not_requested"
    hold_reason: str | None = None

    def public_projection(self) -> dict[str, Any]:
        """Expose outcomes without routing identifiers or raw transport output."""
        return {
            name: getattr(self, name)
            for name in (
                "status",
                "report_date",
                "image_status",
                "verification_level",
                "text_state",
                "image_state",
                "hold_reason",
            )
        }


def personal_chat_id(explicit_chat_id: str | None = None) -> str:
    """Resolve only the explicitly configured personal target."""
    value = (explicit_chat_id or os.environ.get("WEEKLY_BASKET_PERSONAL_CHAT_ID") or "").strip()
    if not value:
        raise WeeklyBasketDeliveryError("personal Feishu chat ID is required")
    if any(separator in value for separator in (",", ";", "\n", "\r")):
        raise WeeklyBasketDeliveryError("personal delivery requires a single chat ID")
    if value.startswith("oc_"):
        raise WeeklyBasketDeliveryError("personal delivery rejects group chat IDs")
    return value


def idempotency_key(chat_id: str, report_date: str, markdown: str) -> str:
    """Preserve the established provider namespace, independent of content."""
    del markdown
    target_hash = hashlib.sha256(chat_id.encode()).hexdigest()[:16]
    week = datetime.strptime(report_date, "%Y%m%d").strftime("%G-W%V")
    return f"weekly-basket:{target_hash}:{week}:text"


def _target_args(target: str, kind: str) -> list[str]:
    if kind == "personal" and not target.startswith("oc_"):
        return ["--user-id", target]
    if kind == "group" and target.startswith("oc_"):
        return ["--chat-id", target]
    raise WeeklyBasketDeliveryError(f"{kind} target does not match its group chat ID type")


def parse_message_id(returncode: int, stdout: str) -> str | None:
    """Return CLI-reported platform acceptance, never infer success from exit alone."""
    try:
        payload = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    if returncode != 0 or not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    data = payload.get("data")
    message_id = data.get("message_id") if isinstance(data, dict) else None
    return (
        message_id
        if isinstance(message_id, str) and re.fullmatch(r"om_[A-Za-z0-9_-]+", message_id)
        else None
    )


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WeeklyBasketDeliveryError("invalid delivery evidence") from exc
    if not isinstance(payload, dict):
        raise WeeklyBasketDeliveryError("delivery evidence must be an object")
    return payload


def _checkpoint(path: Path, record: dict[str, Any]) -> None:
    durable_write(path, (json.dumps(record, sort_keys=True, indent=2) + "\n").encode())


def _view(
    identity: dict[str, Any],
    record: dict[str, Any] | None = None,
    *,
    hold: str | None = None,
    verification: str = "cli_reported_acceptance",
) -> DeliveryReceipt:
    phases = record["phases"] if record else {}
    text = phases.get("text", {}).get("state", "not_started")
    image = phases.get("image", {}).get("state", "not_requested")
    sent = text == "accepted" and image in {"accepted", "not_requested"} and hold is None
    return DeliveryReceipt(
        status="sent" if sent else "failed",
        report_date=identity["report_date"],
        chat_id=identity["target_id"],
        idempotency_key=identity["idempotency_key"],
        markdown_sha256=identity["markdown_sha256"],
        image_status="sent"
        if image == "accepted"
        else "not_requested"
        if image == "not_requested"
        else "failed",
        verification_level=verification
        if sent or verification == "legacy_unverified"
        else "unverified",
        text_state=text,
        image_state=image,
        hold_reason=hold,
    )


def _validate_record(record: dict[str, Any]) -> None:
    if (
        set(record) != {"schema_version", "identity", "phases", "payload"}
        or record["schema_version"] != SCHEMA
    ):
        raise WeeklyBasketDeliveryError("unknown or invalid delivery schema")
    if not isinstance(record["identity"], dict) or not isinstance(record["payload"], dict):
        raise WeeklyBasketDeliveryError("invalid delivery identity/payload")
    _validate_identity(record["identity"])
    phases = record["phases"]
    if not isinstance(phases, dict) or set(phases) != {"text", "image"}:
        raise WeeklyBasketDeliveryError("invalid delivery phases")
    for name, phase in phases.items():
        if not isinstance(phase, dict) or set(phase) != {"state", "message_id"}:
            raise WeeklyBasketDeliveryError("invalid delivery phase")
        state, message_id = phase["state"], phase["message_id"]
        allowed = {"not_started", "inflight", "accepted", "uncertain"}
        if name == "image":
            allowed.add("not_requested")
        if not isinstance(state, str) or state not in allowed:
            raise WeeklyBasketDeliveryError("invalid delivery phase state")
        if message_id is not None and (
            not isinstance(message_id, str) or not re.fullmatch(r"om_[A-Za-z0-9_-]+", message_id)
        ):
            raise WeeklyBasketDeliveryError("invalid delivery message ID")
        if state == "accepted" and message_id is None:
            raise WeeklyBasketDeliveryError("accepted phase requires message ID")
        if state in {"not_started", "not_requested", "inflight"} and message_id is not None:
            raise WeeklyBasketDeliveryError("unattempted phase cannot carry message ID")
    image_state = phases["image"]["state"]
    if record["identity"]["image_required"] == (image_state == "not_requested"):
        raise WeeklyBasketDeliveryError("image requirement conflicts with phase")
    if (
        image_state in {"inflight", "accepted", "uncertain"}
        and phases["text"]["state"] != "accepted"
    ):
        raise WeeklyBasketDeliveryError("image phase requires accepted text")


def _validate_identity(identity: dict[str, Any]) -> None:
    text_fields = {
        "report_date",
        "target_id",
        "target_kind",
        "sender_scope",
        "idempotency_key",
        "markdown_sha256",
    }
    if set(identity) != text_fields | {
        "image_required",
        "image_sha256",
        "image_size",
        "artifact_sha256",
    }:
        raise WeeklyBasketDeliveryError("invalid delivery identity fields")
    if not all(isinstance(identity[key], str) and identity[key] for key in text_fields):
        raise WeeklyBasketDeliveryError("invalid delivery identity values")
    if type(identity["image_required"]) is not bool:
        raise WeeklyBasketDeliveryError("invalid image requirement")
    if not re.fullmatch(r"[0-9a-f]{64}", identity["markdown_sha256"]):
        raise WeeklyBasketDeliveryError("invalid markdown hash")
    for key in ("image_sha256", "artifact_sha256"):
        value = identity[key]
        if value is not None and (
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        ):
            raise WeeklyBasketDeliveryError("invalid payload hash")
    if identity["image_required"] != (identity["image_sha256"] is not None):
        raise WeeklyBasketDeliveryError("inconsistent image identity")
    if identity["image_required"]:
        if type(identity["image_size"]) is not int or identity["image_size"] < 0:
            raise WeeklyBasketDeliveryError("invalid image size")
    elif identity["image_size"] is not None:
        raise WeeklyBasketDeliveryError("unexpected image size")
    _target_args(identity["target_id"], identity["target_kind"])
    if (
        idempotency_key(identity["target_id"], identity["report_date"], "")
        != identity["idempotency_key"]
    ):
        raise WeeklyBasketDeliveryError("inconsistent provider key")


def _legacy_hold(paths: set[Path], identity: dict[str, Any]) -> bool:
    found = False
    for path in sorted(paths):
        if not path.is_file():
            continue
        old = _load(path)
        if "schema_version" in old:
            raise WeeklyBasketDeliveryError("detached or unknown versioned receipt")
        required = {"report_date", "chat_id", "idempotency_key", "markdown_sha256", "status"}
        if not required.issubset(old) or not all(isinstance(old[k], str) for k in required):
            raise WeeklyBasketDeliveryError("legacy receipt is missing historical identity")
        try:
            old_key = idempotency_key(old["chat_id"], old["report_date"], "")
        except ValueError as exc:
            raise WeeklyBasketDeliveryError("invalid legacy report date") from exc
        if old["idempotency_key"] != old_key or not re.fullmatch(
            r"[0-9a-f]{64}", old["markdown_sha256"]
        ):
            raise WeeklyBasketDeliveryError("invalid legacy identity")
        if old_key == identity["idempotency_key"]:
            found = True
            if any(
                old[k] != identity[new]
                for k, new in (
                    ("report_date", "report_date"),
                    ("chat_id", "target_id"),
                    ("markdown_sha256", "markdown_sha256"),
                )
            ):
                raise WeeklyBasketDeliveryError("legacy receipt identity mismatch")
            if old["status"] not in {"sent", "failed", "dry_run"}:
                raise WeeklyBasketDeliveryError("invalid legacy status")
    return found


def _manifest_identity(
    markdown: bytes, date: str, image: Path | None, manifest_path: Path | None
) -> tuple[str | None, str | None, int | None]:
    if manifest_path is None:
        if image is not None:
            raise WeeklyBasketDeliveryError("image delivery requires render manifest")
        return None, None, None
    manifest = _load(manifest_path)
    try:
        files = manifest["files"]
        if (
            manifest["schema_version"] != "weekly_basket.render.v1"
            or manifest["report_date"] != date
        ):
            raise WeeklyBasketDeliveryError("render manifest identity mismatch")
        if files["markdown"]["sha256"] != hashlib.sha256(markdown).hexdigest() or files["markdown"][
            "size"
        ] != len(markdown):
            raise WeeklyBasketDeliveryError("render manifest markdown mismatch")
        artifact = manifest["artifact_sha256"]
        expected = files["png"]["sha256"] if image is not None else None
        if not isinstance(artifact, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact):
            raise WeeklyBasketDeliveryError("invalid render artifact hash")
        if expected is not None and (
            not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)
        ):
            raise WeeklyBasketDeliveryError("invalid render image hash")
        size = files["png"]["size"] if image is not None else None
        if image is not None and (type(size) is not int or size < 0):
            raise WeeklyBasketDeliveryError("invalid render image size")
        return artifact, expected, size
    except (KeyError, TypeError) as exc:
        raise WeeklyBasketDeliveryError("invalid render manifest") from exc


def _freeze(
    slot: Path, markdown: bytes, image: Path | None, expected: str | None, expected_size: int | None
) -> dict[str, str | None]:
    markdown_path = slot / "payload.md"
    durable_write(markdown_path, markdown, 0o400)
    image_path = slot / "report.png" if image is not None else None
    if image_path is not None and image is not None:
        content = image.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected or len(content) != expected_size:
            raise WeeklyBasketDeliveryError("render image hash mismatch")
        durable_write(image_path, content, 0o400)
    return {"markdown": markdown_path.name, "image": image_path.name if image_path else None}


def _payload_valid(slot: Path, record: dict[str, Any]) -> bool:
    try:
        payload, identity = record["payload"], record["identity"]
        if payload != {
            "markdown": "payload.md",
            "image": "report.png" if identity["image_required"] else None,
        }:
            return False
        if sha256_file(slot / "payload.md") != identity["markdown_sha256"]:
            return False
        return (
            not identity["image_required"]
            or sha256_file(slot / "report.png") == identity["image_sha256"]
        )
    except (OSError, KeyError, TypeError):
        return False


def _advance(
    slot: Path, path: Path, record: dict[str, Any], phase_name: str, lark_cli: str
) -> None:
    phase, identity = record["phases"][phase_name], record["identity"]
    if not _payload_valid(slot, record):
        raise WeeklyBasketDeliveryError("payload changed before durable intent")
    phase["state"] = "inflight"
    _checkpoint(path, record)  # A failure here must propagate before any transport call.
    if not _payload_valid(slot, record):
        phase["state"] = "uncertain"
        _checkpoint(path, record)
        return
    command = [
        lark_cli,
        "im",
        "+messages-send",
        "--as",
        "bot",
        *_target_args(identity["target_id"], identity["target_kind"]),
    ]
    if phase_name == "text":
        command.extend(["--markdown", (slot / "payload.md").read_bytes().decode("utf-8")])
    else:
        command.extend(["--image", "report.png"])
    key = identity["idempotency_key"].removesuffix(":text") + ":" + phase_name
    command.extend(["--idempotency-key", key, "--format", "json"])
    try:
        result = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, check=False, timeout=30, cwd=slot
        )
        message_id = parse_message_id(result.returncode, result.stdout)
    except (OSError, subprocess.SubprocessError):
        message_id = None
    phase["message_id"] = message_id
    phase["state"] = "accepted" if message_id and _payload_valid(slot, record) else "uncertain"
    _checkpoint(path, record)  # A failure leaves durable inflight, never automatic retry.


def _deliver_locked(
    identity: dict[str, Any],
    slot: Path,
    legacy_paths: set[Path],
    *,
    markdown: bytes,
    image: Path | None,
    lark_cli: str,
) -> DeliveryReceipt:
    path = slot / "receipt.json"
    if _legacy_hold(legacy_paths, identity):
        return _view(identity, hold="hold_no_send", verification="legacy_unverified")
    if path.exists():
        record = _load(path)
        _validate_record(record)
        if record["identity"] != identity:
            return _view(identity, record, hold="identity_conflict")
    else:
        if any(slot.glob("payload.*")) or (slot / "report.png").exists():
            return _view(identity, hold="orphan_payload")
        payload = _freeze(slot, markdown, image, identity["image_sha256"], identity["image_size"])
        record: dict[str, Any] = {
            "schema_version": SCHEMA,
            "identity": identity,
            "payload": payload,
            "phases": {
                "text": {"state": "not_started", "message_id": None},
                "image": {"state": "not_started" if image else "not_requested", "message_id": None},
            },
        }
        _checkpoint(path, record)
    if not _payload_valid(slot, record):
        return _view(identity, record, hold="payload_conflict")
    phases = record["phases"]
    if any(phase["state"] in {"inflight", "uncertain"} for phase in phases.values()):
        return _view(identity, record, hold="hold_no_send")
    if phases["text"]["state"] == "not_started":
        _advance(slot, path, record, "text", lark_cli)
    if phases["text"]["state"] == "accepted" and phases["image"]["state"] == "not_started":
        _advance(slot, path, record, "image", lark_cli)
    return _view(identity, record)


def send_basket_report(
    markdown: str,
    *,
    report_date: str,
    target_id: str,
    target_kind: str,
    lark_cli: str,
    receipt_path: Path,
    dry_run: bool = False,
    image_path: Path | None = None,
    sender_scope: str | None = None,
    delivery_state_root: Path | None = None,
    legacy_receipt_root: Path | None = None,
    render_manifest_path: Path | None = None,
) -> DeliveryReceipt:
    """Send through one durable weekly slot; ordinary retries never reopen holds."""
    target = target_id.strip()
    if not target or any(separator in target for separator in (",", ";", "\n", "\r")):
        raise WeeklyBasketDeliveryError("delivery requires one explicit target")
    _target_args(target, target_kind)
    content = markdown.encode("utf-8")
    key = idempotency_key(target, report_date, markdown)
    identity = {
        "report_date": report_date,
        "target_id": target,
        "target_kind": target_kind,
        "sender_scope": sender_scope,
        "idempotency_key": key,
        "markdown_sha256": hashlib.sha256(content).hexdigest(),
        "image_required": image_path is not None,
    }
    if dry_run:
        return DeliveryReceipt(
            "dry_run",
            report_date,
            target,
            key,
            identity["markdown_sha256"],
            image_status="dry_run" if image_path else "not_requested",
        )
    if (
        not isinstance(sender_scope, str)
        or not sender_scope.strip()
        or delivery_state_root is None
        or legacy_receipt_root is None
    ):
        raise WeeklyBasketDeliveryError(
            "live delivery requires sender_scope, delivery_state_root and legacy_receipt_root"
        )
    artifact_hash, image_hash, image_size = _manifest_identity(
        content, report_date, image_path, render_manifest_path
    )
    identity.update(artifact_sha256=artifact_hash, image_sha256=image_hash, image_size=image_size)
    slot = delivery_state_root / key.split(":")[1] / key.split(":")[2]
    legacy_paths = {receipt_path}
    # The supplied root is the bounded historical output root, never the whole workspace.
    for candidate in legacy_receipt_root.glob(
        "[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]/delivery/*.json"
    ):
        try:
            week = datetime.strptime(candidate.parent.parent.name, "%Y%m%d").strftime("%G-W%V")
        except ValueError:
            continue
        if week == key.split(":")[2]:
            legacy_paths.add(candidate)
    with exclusive_lock(slot / "delivery.lock"):
        return _deliver_locked(
            identity, slot, legacy_paths, markdown=content, image=image_path, lark_cli=lark_cli
        )


def send_personal_basket_report(markdown: str, *, chat_id: str, **kwargs: Any) -> DeliveryReceipt:
    """Keep the personal wrapper while requiring explicit live state configuration."""
    return send_basket_report(
        markdown, target_id=personal_chat_id(chat_id), target_kind="personal", **kwargs
    )


__all__ = [
    "DeliveryReceipt",
    "WeeklyBasketDeliveryError",
    "idempotency_key",
    "parse_message_id",
    "personal_chat_id",
    "send_basket_report",
    "send_personal_basket_report",
]
