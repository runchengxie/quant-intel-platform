"""Research-only cashflow artifact delivery to an explicit Feishu test group."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

CASHFLOW_SELECTION_SCHEMA = "strategy_app.cashflow.selection.v1"
CASHFLOW_EXECUTABLE_SCHEMA = "strategy_app.cashflow.executable.v1"
DELIVERY_SCHEMA = "cashflow_feishu_delivery.v1"
PUBLICATION_SCHEMA = "strategy_pipeline.cashflow.publication.v1"
POLICY_ID = "cashflow_quality_top50_v1.quarterly_fcf_cap10.v1"
EXPECTED_POLICY = {
    "strategy_id": "cashflow_quality_top50_v1",
    "policy_id": POLICY_ID,
    "top_n": 50,
    "max_weight": 0.10,
    "rebalance_frequency": "quarterly",
    "signal_timing": "source_close_to_next_open",
}


class CashflowDeliveryError(ValueError):
    """Raised when a cashflow artifact is not safe to deliver."""


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CashflowDeliveryError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CashflowDeliveryError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CashflowDeliveryError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date(value: Any, *, label: str) -> str:
    text = str(value or "").replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise CashflowDeliveryError(f"{label} must use YYYYMMDD")
    return text


def load_selection(
    path: Path, *, expected_source_date: str, expected_signal_date: str
) -> dict[str, Any]:
    artifact = _read_object(path, label="cashflow selection")
    expected = {
        "schema_version": CASHFLOW_SELECTION_SCHEMA,
        "status": "passed",
        "research_only": True,
        "eligible_for_live": False,
        "source_date": _date(expected_source_date, label="expected source_date"),
        "signal_date": _date(expected_signal_date, label="expected signal_date"),
    }
    for field, value in expected.items():
        actual = (
            _date(artifact.get(field), label=field)
            if field.endswith("_date")
            else artifact.get(field)
        )
        if actual != value:
            raise CashflowDeliveryError(
                f"cashflow selection {field}={actual!r}, expected {value!r}"
            )
    if not str(artifact.get("strategy_id") or "").strip():
        raise CashflowDeliveryError("cashflow selection strategy_id is required")
    if artifact.get("policy_id") != POLICY_ID:
        raise CashflowDeliveryError("cashflow selection policy is unsupported")
    if artifact.get("policy") != EXPECTED_POLICY:
        raise CashflowDeliveryError("cashflow selection policy mapping is not frozen")
    content_hash = str(artifact.get("content_sha256") or "")
    if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
        raise CashflowDeliveryError("cashflow selection content_sha256 is invalid")
    targets = artifact.get("targets")
    if (
        not isinstance(targets, list)
        or not targets
        or not all(isinstance(row, Mapping) for row in targets)
    ):
        raise CashflowDeliveryError("cashflow selection targets must be a non-empty list")
    symbols = [str(row.get("symbol") or "") for row in targets]
    weights = [float(row.get("target_weight", 0.0)) for row in targets]
    if any(not symbol for symbol in symbols) or len(symbols) != len(set(symbols)):
        raise CashflowDeliveryError("cashflow selection targets contain duplicate or empty symbols")
    if any(weight <= 0 for weight in weights) or abs(sum(weights) - 1.0) > 1e-8:
        raise CashflowDeliveryError("cashflow selection target weights must sum to one")
    return artifact


def load_executable(
    path: Path, *, expected_source_date: str, expected_signal_date: str
) -> dict[str, Any]:
    """Load and validate a lot-rounded executable research artifact."""
    artifact = _read_object(path, label="cashflow executable portfolio")
    expected = {
        "schema_version": CASHFLOW_EXECUTABLE_SCHEMA,
        "status": "passed",
        "research_only": True,
        "eligible_for_live": False,
        "source_date": _date(expected_source_date, label="expected source_date"),
        "signal_date": _date(expected_signal_date, label="expected signal_date"),
    }
    for field, value in expected.items():
        actual = (
            _date(artifact.get(field), label=field)
            if field.endswith("_date")
            else artifact.get(field)
        )
        if actual != value:
            raise CashflowDeliveryError(
                f"cashflow executable {field}={actual!r}, expected {value!r}"
            )
    if not str(artifact.get("strategy_id") or "").strip():
        raise CashflowDeliveryError("cashflow executable strategy_id is required")
    content_hash = str(artifact.get("content_sha256") or "")
    if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
        raise CashflowDeliveryError("cashflow executable content_sha256 is invalid")
    policy = artifact.get("policy")
    if not isinstance(policy, Mapping) or float(policy.get("portfolio_value", 0.0)) <= 0:
        raise CashflowDeliveryError("cashflow executable policy is invalid")
    targets = artifact.get("targets")
    if (
        not isinstance(targets, list)
        or not targets
        or not all(isinstance(row, Mapping) for row in targets)
    ):
        raise CashflowDeliveryError("cashflow executable targets must be a non-empty list")
    for row in targets:
        shares = int(row.get("shares", 0))
        if shares <= 0 or shares % 100 != 0:
            raise CashflowDeliveryError("cashflow executable shares must use 100-share lots")
        if float(row.get("actual_amount", 0.0)) <= 0 or float(row.get("actual_weight", 0.0)) <= 0:
            raise CashflowDeliveryError("cashflow executable actual position fields are invalid")
    return artifact


def validate_publication_receipt(
    path: Path, *, selection_path: Path, artifact: Mapping[str, Any]
) -> dict[str, Any]:
    """Require the immutable shadow-publication contract before delivery."""
    receipt = _read_object(path, label="cashflow publication receipt")
    expected = {
        "schema_version": PUBLICATION_SCHEMA,
        "publication_tier": "feishu_shadow",
        "status": "passed",
        "research_only": True,
        "eligible_for_live": False,
        "strategy_id": artifact["strategy_id"],
        "policy_id": artifact["policy_id"],
        "source_date": artifact["source_date"],
        "signal_date": artifact["signal_date"],
        "selection_sha256": _sha256_file(selection_path),
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise CashflowDeliveryError(
                f"cashflow publication receipt {field}={receipt.get(field)!r}, expected {value!r}"
            )
    publication_hash = str(receipt.get("publication_sha256") or "")
    if len(publication_hash) != 64 or any(
        char not in "0123456789abcdef" for char in publication_hash
    ):
        raise CashflowDeliveryError("cashflow publication_sha256 is invalid")
    identity = {
        "strategy_id": receipt["strategy_id"],
        "policy_id": receipt["policy_id"],
        "source_date": receipt["source_date"],
        "signal_date": receipt["signal_date"],
        "selection_sha256": receipt["selection_sha256"],
        "readiness_sha256": receipt.get("readiness_sha256"),
    }
    expected_publication_hash = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if publication_hash != expected_publication_hash:
        raise CashflowDeliveryError("cashflow publication_sha256 does not match receipt identity")
    return receipt


def validate_executable_receipt(
    path: Path, *, selection_path: Path, artifact: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the immutable executable receipt before Feishu delivery."""
    receipt = _read_object(path, label="cashflow executable receipt")
    expected = {
        "schema_version": CASHFLOW_EXECUTABLE_SCHEMA,
        "status": "passed",
        "research_only": True,
        "eligible_for_live": False,
        "strategy_id": artifact["strategy_id"],
        "source_date": artifact["source_date"],
        "signal_date": artifact["signal_date"],
        "content_sha256": artifact["content_sha256"],
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise CashflowDeliveryError(
                f"cashflow executable receipt {field}={receipt.get(field)!r}, expected {value!r}"
            )
    return receipt


def _short_symbol(value: Any) -> str:
    return str(value or "").split(".", maxsplit=1)[0]


def render_markdown(artifact: Mapping[str, Any]) -> str:
    targets = artifact["targets"]
    if not isinstance(targets, list):
        raise CashflowDeliveryError("cashflow selection targets must be a list")
    executable = artifact.get("schema_version") == CASHFLOW_EXECUTABLE_SCHEMA
    lines = [
        "ð ç°éæµè´¨éï½å¯æ§è¡ç»åç ç©¶å½±å­æ¨é" if executable else "ð ç°éæµè´¨é Top50ï½ç ç©¶å½±å­æ¨é",
        "",
        f"ä¿¡å·ï¼{str(artifact['source_date'])[:4]}-{str(artifact['source_date'])[4:6]}-{str(artifact['source_date'])[6:]} æ¶ç â "
        f"{str(artifact['signal_date'])[:4]}-{str(artifact['signal_date'])[4:6]}-{str(artifact['signal_date'])[6:]} å¼çç®æ ",
        f"ç­ç¥ï¼{artifact['strategy_id']}",
        f"Policyï¼{artifact['policy_id']}",
        f"PIT è´¨éï¼{str(artifact.get('pit_quality') or 'verified').upper()}",
        "",
        "å¯æ§è¡æä»ï¼å®éè¡æ°ï¼ï¼" if executable else "ç®æ æä»ï¼",
    ]
    for row in targets:
        if executable:
            lines.append(
                f"- {_short_symbol(row.get('symbol'))} {row.get('name', '')}ï¼"
                f"{int(row.get('shares', 0)):,} è¡ï¼å®éæé {float(row.get('actual_weight', 0.0)):.1%}ï¼"
                f"åå·® {float(row.get('weight_deviation', 0.0)):+.1%}"
            )
        else:
            lines.append(
                f"- {_short_symbol(row.get('symbol'))} {row.get('name', '')}ï¼"
                f"{float(row['target_weight']):.1%}"
                f"ï¼{'æ°å¢' if row.get('is_new') else 'è°æ´'}ï¼"
            )
    lines.extend(
        [
            "",
            (
                f"åèèµéï¼Â¥{float(artifact.get('policy', {}).get('portfolio_value', 0.0)):,.0f}ï¼"
                f"ç°éï¼Â¥{float(artifact.get('cash_amount', 0.0)):,.0f}ã"
                if executable
                else ""
            ),
            "â ï¸ ç ç©¶å½±å­ä¿¡å·ï¼ä¸ææå®çæä»¤ï¼æªéªè¯æäº¤ãå®¹éåå²å»ææ¬ã",
        ]
    )
    return "\n".join(lines) + "\n"


def _message_id(stdout: str) -> str | None:
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping) or payload.get("ok") is False:
        return None
    data = payload.get("data")
    if isinstance(data, Mapping) and str(data.get("message_id") or "").strip():
        return str(data["message_id"])
    return str(payload.get("message_id")) if payload.get("message_id") else None


def _target_hash(chat_id: str) -> str:
    return hashlib.sha256(f"lark-chat\0{chat_id}".encode()).hexdigest()


def _idempotency_key(artifact: Mapping[str, Any], chat_id: str) -> str:
    material = "\0".join(
        (
            str(artifact["strategy_id"]),
            str(artifact["policy_id"]),
            str(artifact["signal_date"]),
            chat_id,
            str(artifact["content_sha256"]),
        )
    )
    return "cashflow-" + hashlib.sha256(material.encode()).hexdigest()[:24]


def _send(
    *, lark_cli: str, chat_id: str, markdown: str, artifact: Mapping[str, Any]
) -> dict[str, Any]:
    key = _idempotency_key(artifact, chat_id)
    result = subprocess.run(  # noqa: S603 - lark CLI is an explicit operator-configured binary
        [
            lark_cli,
            "im",
            "+messages-send",
            "--chat-id",
            chat_id,
            "--markdown",
            markdown,
            "--idempotency-key",
            key,
            "--as",
            "bot",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    message_id = _message_id(result.stdout)
    ok = result.returncode == 0 and message_id is not None
    return {
        "target_sha256": _target_hash(chat_id),
        "status": "sent" if ok else "failed",
        "idempotency_key": key,
        "message_id": message_id,
        "error": None if ok else (result.stderr or result.stdout)[-500:],
    }


def _previous_attempts(
    path: Path,
    artifact: Mapping[str, Any],
    selection_sha256: str,
    publication_receipt_sha256: str,
) -> dict[str, Mapping[str, Any]]:
    if not path.is_file():
        return {}
    previous = _read_object(path, label="previous cashflow delivery receipt")
    if previous.get("success") is False:
        return {}
    expected = {
        "schema_version": DELIVERY_SCHEMA,
        "strategy_id": artifact["strategy_id"],
        "policy_id": artifact["policy_id"],
        "signal_date": artifact["signal_date"],
        "content_sha256": artifact["content_sha256"],
        "selection_sha256": selection_sha256,
        "publication_receipt_sha256": publication_receipt_sha256,
    }
    mismatches = [
        field for field, value in expected.items() if previous.get(field) != value
    ]
    if mismatches:
        raise CashflowDeliveryError(
            "previous cashflow delivery receipt identity mismatch: " + ",".join(mismatches)
        )
    rows = previous.get("targets")
    if not isinstance(rows, list):
        return {}
    return {
        str(row["target_sha256"]): row
        for row in rows
        if isinstance(row, Mapping) and row.get("target_sha256")
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_failure_receipt(
    path: Path,
    *,
    source_date: str,
    signal_date: str,
    error: str,
) -> None:
    """Persist an alertable delivery failure without creating a sent state."""
    _atomic_json(
        path,
        {
            "schema_version": DELIVERY_SCHEMA,
            "status": "failed",
            "success": False,
            "dry_run": False,
            "source_date": source_date,
            "signal_date": signal_date,
            "error": error[-1000:],
            "created_at": datetime.now(UTC).isoformat(),
            "targets": [],
        },
    )


def deliver(
    *,
    artifact: Mapping[str, Any],
    selection_path: Path,
    publication_receipt_path: Path,
    receipt_path: Path,
    chat_ids: Sequence[str],
    lark_cli: str,
    dry_run: bool,
    artifact_kind: str = "selection",
) -> dict[str, Any]:
    recipients = tuple(
        dict.fromkeys(str(chat_id).strip() for chat_id in chat_ids if str(chat_id).strip())
    )
    if not recipients:
        raise CashflowDeliveryError("cashflow delivery requires at least one explicit Feishu chat")
    markdown = render_markdown(artifact)
    selection_sha256 = _sha256_file(selection_path)
    if artifact_kind == "executable":
        validate_executable_receipt(
            publication_receipt_path,
            selection_path=selection_path,
            artifact=artifact,
        )
    elif artifact_kind == "selection":
        validate_publication_receipt(
            publication_receipt_path,
            selection_path=selection_path,
            artifact=artifact,
        )
    else:
        raise CashflowDeliveryError(f"unsupported cashflow artifact kind: {artifact_kind}")
    publication_receipt_sha256 = _sha256_file(publication_receipt_path)
    previous = _previous_attempts(
        receipt_path, artifact, selection_sha256, publication_receipt_sha256
    )
    attempts: list[dict[str, Any]] = []
    for chat_id in recipients:
        target_hash = _target_hash(chat_id)
        old = previous.get(target_hash)
        if isinstance(old, Mapping) and old.get("status") in {"sent", "already_sent"}:
            attempts.append({**dict(old), "status": "already_sent"})
        elif dry_run:
            attempts.append(
                {
                    "target_sha256": target_hash,
                    "status": "dry_run",
                    "idempotency_key": _idempotency_key(artifact, chat_id),
                    "message_id": None,
                    "error": None,
                }
            )
        else:
            attempts.append(_send(lark_cli=lark_cli, chat_id=chat_id, markdown=markdown, artifact=artifact))
    success = all(row["status"] in {"sent", "already_sent"} for row in attempts)
    receipt = {
        "schema_version": DELIVERY_SCHEMA,
        "strategy_id": artifact["strategy_id"],
        "policy_id": artifact["policy_id"],
        "source_date": artifact["source_date"],
        "signal_date": artifact["signal_date"],
        "content_sha256": artifact["content_sha256"],
        "selection_sha256": selection_sha256,
        "publication_receipt_sha256": publication_receipt_sha256,
        "success": success,
        "dry_run": dry_run,
        "created_at": datetime.now(UTC).isoformat(),
        "targets": attempts,
    }
    _atomic_json(receipt_path, receipt)
    return receipt


__all__ = [
    "CashflowDeliveryError",
    "CASHFLOW_EXECUTABLE_SCHEMA",
    "deliver",
    "load_executable",
    "load_selection",
    "render_markdown",
    "validate_executable_receipt",
    "validate_publication_receipt",
    "write_failure_receipt",
]
