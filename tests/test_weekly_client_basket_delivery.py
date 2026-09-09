from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from a_share_daily.weekly_client_basket_delivery import (
    WeeklyBasketDeliveryError,
    idempotency_key,
    personal_chat_id,
    send_personal_basket_report,
)


def _ok() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["lark-cli"], 0, stdout="{}", stderr="")


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
    assert json.loads((tmp_path / "receipt.json").read_text())["identity"] == "app"


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
    )

    assert receipt.status == "sent"
    assert "--as" in calls[0] and calls[0][calls[0].index("--as") + 1] == "bot"
    assert "--chat-id" in calls[0] and calls[0][calls[0].index("--chat-id") + 1] == "ou_owner"
    assert calls[0][calls[0].index("--idempotency-key") + 1] == idempotency_key(
        "ou_owner", "20260914", "# test"
    )
