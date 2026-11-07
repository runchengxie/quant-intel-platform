from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from a_share_daily.weekly_client_basket_delivery import (
    WeeklyBasketDeliveryError,
    idempotency_key,
    personal_chat_id,
    send_basket_report,
    send_personal_basket_report,
)


def _ok() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["lark-cli"], 0, stdout='{"ok":true,"data":{"message_id":"om_test"}}', stderr=""
    )


def test_no_send_does_not_invoke_lark_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("must not send"),
    )

    receipt = send_personal_basket_report(
        "# test",
        report_date="20260914",
        chat_id="ou_owner",
        lark_cli="/bin/lark-cli",
        receipt_path=tmp_path / "receipt.json",
        dry_run=True,
    )

    assert receipt.status == "dry_run"
    assert not (tmp_path / "receipt.json").exists()


def test_missing_personal_target_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEEKLY_BASKET_PERSONAL_CHAT_ID", raising=False)
    monkeypatch.setenv("MARKET_INTEL_CLIENT_CHAT_ID", "client-group")

    with pytest.raises(WeeklyBasketDeliveryError, match="personal"):
        personal_chat_id(None)


def test_group_target_list_is_rejected() -> None:
    with pytest.raises(WeeklyBasketDeliveryError, match="single"):
        personal_chat_id("ou_owner,oc_group")


def test_send_uses_app_identity_and_stable_idempotency_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or _ok(),
    )

    receipt = send_personal_basket_report(
        "# test",
        report_date="20260914",
        chat_id="ou_owner",
        lark_cli="/bin/lark-cli",
        receipt_path=tmp_path / "receipt.json",
        sender_scope="test-app",
        delivery_state_root=tmp_path / "state",
        legacy_receipt_root=tmp_path / "legacy",
    )

    assert receipt.status == "sent"
    assert "--as" in calls[0] and calls[0][calls[0].index("--as") + 1] == "bot"
    assert "--user-id" in calls[0] and calls[0][calls[0].index("--user-id") + 1] == "ou_owner"
    assert "--chat-id" not in calls[0]
    assert calls[0][calls[0].index("--idempotency-key") + 1] == idempotency_key(
        "ou_owner", "20260914", "# test"
    )
    assert idempotency_key("ou_owner", "20260914", "changed copy") == receipt.idempotency_key
    assert receipt.idempotency_key.endswith(":text")


def test_send_can_follow_text_with_app_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    image = tmp_path / "report.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or _ok(),
    )

    receipt = send_personal_basket_report(
        "# test",
        report_date="20260914",
        chat_id="ou_owner",
        lark_cli="/bin/lark-cli",
        receipt_path=tmp_path / "receipt.json",
        image_path=image,
        sender_scope="test-app",
        delivery_state_root=tmp_path / "state",
        legacy_receipt_root=tmp_path / "legacy",
        render_manifest_path=_manifest(tmp_path, image, "# test"),
    )

    assert receipt.image_status == "sent"
    assert len(calls) == 2
    assert "--user-id" in calls[1] and calls[1][calls[1].index("--user-id") + 1] == "ou_owner"
    assert "--image" in calls[1]
    assert calls[1][calls[1].index("--image") + 1] == "report.png"


def test_legacy_recovery_holds_failed_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    image = tmp_path / "report.png"
    image.write_bytes(b"png")
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "status": "sent",
                "report_date": "20260914",
                "chat_id": "ou_owner",
                "idempotency_key": idempotency_key("ou_owner", "20260914", "old"),
                "markdown_sha256": hashlib.sha256(b"# changed").hexdigest(),
                "identity": "app",
                "returncode": 0,
                "stderr": "",
                "image_status": "failed",
            }
        )
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or _ok(),
    )

    receipt = send_personal_basket_report(
        "# changed",
        report_date="20260914",
        chat_id="ou_owner",
        lark_cli="/bin/lark-cli",
        receipt_path=receipt_path,
        image_path=image,
        sender_scope="test-app",
        delivery_state_root=tmp_path / "state",
        legacy_receipt_root=tmp_path / "legacy",
        render_manifest_path=_manifest(tmp_path, image, "# changed"),
    )

    assert receipt.status == "failed"
    assert receipt.verification_level == "legacy_unverified"
    assert receipt.hold_reason == "hold_no_send"
    assert calls == []


def test_group_send_uses_chat_id_and_independent_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or _ok(),
    )

    receipt = send_basket_report(
        "# test",
        report_date="20260914",
        target_id="oc_quant",
        target_kind="group",
        lark_cli="/bin/lark-cli",
        receipt_path=tmp_path / "group.json",
        sender_scope="test-app",
        delivery_state_root=tmp_path / "state",
        legacy_receipt_root=tmp_path / "legacy",
    )

    assert receipt.status == "sent"
    assert "--chat-id" in calls[0]
    assert calls[0][calls[0].index("--chat-id") + 1] == "oc_quant"
    assert "--user-id" not in calls[0]


def test_target_kind_and_id_must_match(tmp_path: Path) -> None:
    with pytest.raises(WeeklyBasketDeliveryError, match="group chat ID"):
        send_basket_report(
            "# test",
            report_date="20260914",
            target_id="ou_owner",
            target_kind="group",
            lark_cli="/bin/lark-cli",
            receipt_path=tmp_path / "receipt.json",
            dry_run=True,
        )


def _manifest(root: Path, image: Path, markdown: str) -> Path:
    path = root / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "weekly_basket.render.v1",
                "report_date": "20260914",
                "artifact_sha256": "a" * 64,
                "files": {
                    "markdown": {
                        "sha256": hashlib.sha256(markdown.encode()).hexdigest(),
                        "size": len(markdown.encode()),
                    },
                    "png": {
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        "size": image.stat().st_size,
                    },
                },
            }
        )
    )
    return path
