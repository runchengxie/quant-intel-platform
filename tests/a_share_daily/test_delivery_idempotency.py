from __future__ import annotations

import json
from pathlib import Path

from a_share_daily.delivery import report_delivery, senders, state


def _artifacts(*, sha256: str = "a" * 64) -> list[dict[str, object]]:
    return [{"role": "morning_report", "path": "/tmp/report.md", "sha256": sha256}]


def test_delivery_receipt_has_stable_identity_and_message_ids() -> None:
    payload = state.build_delivery_receipt(
        kind="morning",
        trade_date="20260908",
        signal_date="20260909",
        mode="lark",
        success=True,
        routes={"lark_text": True},
        artifacts=_artifacts(),
        message_ids={"lark_text": ["om_123"]},
        lark_targets=["oc_internal"],
        hermes_targets=[],
    )

    assert payload["schema_version"] == state.DELIVERY_SCHEMA
    assert payload["kind"] == "morning"
    assert payload["trade_date"] == "20260908"
    assert payload["signal_date"] == "20260909"
    assert payload["success"] is True
    assert payload["message_ids"] == {"lark_text": ["om_123"]}
    assert len(payload["idempotency_key"]) == 64


def test_delivery_identity_is_same_for_exact_retry_and_changes_with_content() -> None:
    common = {
        "kind": "morning",
        "trade_date": "20260908",
        "signal_date": "20260909",
        "mode": "lark",
        "success": True,
        "routes": {"lark_text": True},
        "lark_targets": ["oc_internal"],
        "hermes_targets": [],
    }

    first = state.build_delivery_receipt(
        **common,
        artifacts=_artifacts(),
        message_ids={"lark_text": ["om_first"]},
    )
    retry = state.build_delivery_receipt(
        **common,
        artifacts=_artifacts(),
        message_ids={"lark_text": ["om_retry"]},
    )
    changed = state.build_delivery_receipt(
        **common,
        artifacts=_artifacts(sha256="b" * 64),
        message_ids=None,
    )

    assert retry["idempotency_key"] == first["idempotency_key"]
    assert changed["idempotency_key"] != first["idempotency_key"]


def test_successful_receipt_matches_only_same_identity(tmp_path: Path) -> None:
    receipt_path = tmp_path / "morning_latest.json"
    payload = state.build_delivery_receipt(
        kind="morning",
        trade_date="20260908",
        signal_date="20260909",
        mode="lark",
        success=True,
        routes={"lark_text": True},
        artifacts=_artifacts(),
        message_ids={"lark_text": ["om_123"]},
        lark_targets=["oc_internal"],
        hermes_targets=[],
    )
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    assert state.has_successful_delivery(receipt_path, payload["idempotency_key"]) is True
    assert state.has_successful_delivery(receipt_path, "0" * 64) is False


def test_report_delivery_skips_exact_successful_retry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(tmp_path))
    context = senders._DeliveryContext(
        mode="lark",
        chat_id="oc_internal",
        user_id=None,
        hermes_target=None,
        hermes_cli=None,
        lark_cli="/bin/lark-cli",
        hermes_targets=[],
        lark_targets=["oc_internal"],
    )
    artifacts = _artifacts()
    key = state.delivery_idempotency_key(
        kind="evening_internal",
        trade_date="20260908",
        signal_date="20260909",
        mode="lark",
        routes={},
        artifacts=artifacts,
        lark_targets=context.lark_targets,
        hermes_targets=context.hermes_targets,
    )
    payload = state.build_delivery_receipt(
        kind="evening_internal",
        trade_date="20260908",
        signal_date="20260909",
        mode="lark",
        success=True,
        routes={"lark_text": True},
        artifacts=artifacts,
        message_ids={"lark_text": ["om_123"]},
        lark_targets=context.lark_targets,
        hermes_targets=context.hermes_targets,
    )
    assert payload["idempotency_key"] == key
    (tmp_path / "evening_internal_latest.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        senders,
        "_send_lark_markdown",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate send")),
    )

    assert (
        report_delivery._deliver_markdown_files_and_images(
            kind="evening_internal",
            trade_date="20260908",
            signal_date="20260909",
            context=context,
            text_files=[],
            image_paths=[],
            artifacts=artifacts,
            webhook_enabled_env="EVENING_SEND_WEBHOOK",
        )
        is True
    )
