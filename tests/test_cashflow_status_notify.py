from __future__ import annotations

import json
from pathlib import Path

import pytest

from a_share_daily import cashflow_status_notify as status_notify


def _status() -> dict[str, object]:
    return {
        "schema_version": "cashflow_status_input.v1",
        "strategy_id": "cashflow_quality_top50_v1",
        "policy_id": "cashflow_quality_top50_v1.quarterly_fcf_cap10.v1",
        "status": "blocked",
        "stage": "readiness",
        "source_date": "20260904",
        "signal_date": "20260907",
        "reason": "historical_revision_not_safe",
        "detail": "PIT audit blocked",
        "no_target_artifact": True,
    }


def test_render_status_markdown_is_status_only() -> None:
    markdown = status_notify.render_status_markdown(_status())

    assert "ç°éæµç­ç¥ï½ç ç©¶ç¶æéç¥" in markdown
    assert "BLOCKED" in markdown
    assert "historical_revision_not_safe" in markdown
    assert "æªçæç®æ æä»" in markdown
    assert "target_weight" not in markdown
    assert "000001" not in markdown


def test_deliver_status_dry_run_is_idempotent_and_explicit(tmp_path: Path) -> None:
    receipt_path = tmp_path / "status-receipt.json"
    first = status_notify.deliver_status(
        status=_status(),
        receipt_path=receipt_path,
        chat_ids=("oc_test",),
        lark_cli="lark-cli",
        dry_run=True,
    )
    second = status_notify.deliver_status(
        status=_status(),
        receipt_path=receipt_path,
        chat_ids=("oc_test",),
        lark_cli="lark-cli",
        dry_run=True,
    )

    assert first["success"] is True
    assert first["status"] == "dry_run"
    assert second["chats"][0]["status"] == "already_sent"
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == status_notify.STATUS_SCHEMA
    assert "targets" not in receipt
    assert "selection" not in receipt


def test_deliver_status_requires_confirmation_for_real_send(tmp_path: Path) -> None:
    with pytest.raises(status_notify.CashflowStatusError, match="confirmation"):
        status_notify.deliver_status(
            status=_status(),
            receipt_path=tmp_path / "status-receipt.json",
            chat_ids=("oc_test",),
            lark_cli="lark-cli",
            dry_run=False,
        )


def test_deliver_status_sends_only_to_explicit_chat_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": '{"ok":true}', "stderr": ""},
        )()

    monkeypatch.setattr(status_notify.subprocess, "run", fake_run)
    receipt_path = tmp_path / "status-receipt.json"
    first = status_notify.deliver_status(
        status=_status(),
        receipt_path=receipt_path,
        chat_ids=("oc_test_a", "oc_test_b"),
        lark_cli="lark-cli",
        dry_run=False,
        send_confirmation="I_UNDERSTAND_TEST_GROUP_ONLY",
    )
    second = status_notify.deliver_status(
        status=_status(),
        receipt_path=receipt_path,
        chat_ids=("oc_test_a", "oc_test_b"),
        lark_cli="lark-cli",
        dry_run=False,
        send_confirmation="I_UNDERSTAND_TEST_GROUP_ONLY",
    )

    assert first["success"] is True
    assert second["chats"][0]["status"] == "already_sent"
    assert len(calls) == 2
    assert all("--chat-id" in command for command in calls)
    assert all("--idempotency-key" in command for command in calls)


def test_real_send_is_not_suppressed_by_a_previous_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(status_notify.subprocess, "run", fake_run)
    receipt_path = tmp_path / "status-receipt.json"
    status_notify.deliver_status(
        status=_status(),
        receipt_path=receipt_path,
        chat_ids=("oc_test",),
        lark_cli="lark-cli",
        dry_run=True,
    )
    sent = status_notify.deliver_status(
        status=_status(),
        receipt_path=receipt_path,
        chat_ids=("oc_test",),
        lark_cli="lark-cli",
        dry_run=False,
        send_confirmation="I_UNDERSTAND_TEST_GROUP_ONLY",
    )

    assert sent["status"] == "sent"
    assert sent["chats"][0]["status"] == "sent"
    assert len(calls) == 1


def test_deliver_status_rejects_target_payload_and_missing_chat_ids(tmp_path: Path) -> None:
    with pytest.raises(status_notify.CashflowStatusError, match="target-like"):
        status_notify.deliver_status(
            status={**_status(), "targets": [{"symbol": "000001.SZ"}]},
            receipt_path=tmp_path / "status-receipt.json",
            chat_ids=("oc_test",),
            lark_cli="lark-cli",
            dry_run=True,
        )

    with pytest.raises(status_notify.CashflowStatusError, match="chat"):
        status_notify.deliver_status(
            status=_status(),
            receipt_path=tmp_path / "status-receipt.json",
            chat_ids=(),
            lark_cli="lark-cli",
            dry_run=True,
        )

