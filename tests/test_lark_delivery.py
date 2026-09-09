from __future__ import annotations

import subprocess
from typing import Any

import pytest

from a_share_daily.delivery import senders
from a_share_daily.delivery.targets import _lark_target_arg_sets, resolve_delivery_targets


def _fake_run(
    returncode: int, stdout: str = "", stderr: str = ""
) -> tuple[Any, list[dict[str, Any]]]:
    """Build a fake subprocess.run that records calls and returns a fixed code."""

    calls: list[dict[str, Any]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": list(cmd), "cwd": cwd, "env": env})
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    return fake_run, calls


def test_run_lark_returns_true_on_zero_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake, calls = _fake_run(0)
    monkeypatch.setattr(senders.subprocess, "run", fake)

    assert senders._run_lark(["lark-cli", "im", "+messages-send"]) is True
    assert not capsys.readouterr().err
    assert len(calls) == 1


def test_run_lark_returns_false_on_nonzero_and_prints_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake, _ = _fake_run(3, stdout="", stderr="boom")
    monkeypatch.setattr(senders.subprocess, "run", fake)

    assert senders._run_lark(["lark-cli", "whoami"]) is False
    err = capsys.readouterr().err
    assert "lark-cli returned 3" in err
    assert "boom" in err


def test_run_lark_returns_false_when_subprocess_raises(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise FileNotFoundError("no cli")

    monkeypatch.setattr(senders.subprocess, "run", boom)

    assert senders._run_lark(["lark-cli", "whoami"]) is False
    assert "lark-cli failed" in capsys.readouterr().err


def test_send_lark_markdown_skips_without_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("A_SHARE_FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("A_SHARE_FEISHU_USER_ID", raising=False)
    monkeypatch.delenv("FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_USER_ID", raising=False)
    ran: dict[str, bool] = {"value": False}

    def fake_run_lark(*_args: Any, **_kwargs: Any) -> bool:
        ran["value"] = True
        return True

    monkeypatch.setattr(senders, "_run_lark", fake_run_lark)

    assert senders._send_lark_markdown("hello", lark_cli="/bin/echo") is False
    assert ran["value"] is False


def test_send_lark_markdown_sends_to_chat_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_one,oc_two")
    calls: list[list[str]] = []

    def fake_run_lark(cmd: list[str], **_kwargs: Any) -> bool:
        calls.append(cmd)
        return True

    monkeypatch.setattr(senders, "_run_lark", fake_run_lark)

    assert senders._send_lark_markdown("日报", lark_cli="/bin/echo") is True
    assert [call[call.index("--chat-id") + 1] for call in calls] == ["oc_one", "oc_two"]
    for call in calls:
        assert call[0] == "/bin/echo"
        assert call[1:3] == ["im", "+messages-send"]
        assert "--markdown" in call
        assert "日报" in call
        assert "--as" in call and call[call.index("--as") + 1] == "bot"
        assert "--idempotency-key" in call
        assert "--format" in call and call[call.index("--format") + 1] == "json"


def test_send_lark_markdown_stable_scope_ignores_dynamic_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_one")
    calls: list[list[str]] = []

    def fake_run_lark(cmd: list[str], **_kwargs: Any) -> bool:
        calls.append(cmd)
        return True

    monkeypatch.setattr(senders, "_run_lark", fake_run_lark)
    scope = ("evening_internal", "20260817", "evening_review.md")

    assert senders._send_lark_markdown(
        "生成时间 19:05", lark_cli="/bin/echo", idempotency_scope=scope
    )
    assert senders._send_lark_markdown(
        "生成时间 19:11", lark_cli="/bin/echo", idempotency_scope=scope
    )
    assert senders._send_lark_markdown(
        "生成时间 19:11",
        lark_cli="/bin/echo",
        idempotency_scope=("evening_internal", "20260817", "evening_summary.md"),
    )

    keys = [call[call.index("--idempotency-key") + 1] for call in calls]
    assert len(keys) == 3
    assert keys[0] == keys[1]
    assert keys[1] != keys[2]


def test_send_lark_markdown_returns_false_if_any_target_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_one,oc_two")

    def fake_run_lark(cmd: list[str], **_kwargs: Any) -> bool:
        # Fail the second target only.
        return cmd[cmd.index("--chat-id") + 1] != "oc_two"

    monkeypatch.setattr(senders, "_run_lark", fake_run_lark)

    assert senders._send_lark_markdown("x", lark_cli="/bin/echo") is False


def test_send_lark_markdown_collects_confirmed_message_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_one")
    fake, _ = _fake_run(0, stdout='{"ok":true,"data":{"message_id":"om_123"}}')
    monkeypatch.setattr(senders.subprocess, "run", fake)
    message_ids: list[str] = []

    assert (
        senders._send_lark_markdown("日报", lark_cli="/bin/echo", message_ids=message_ids) is True
    )
    assert message_ids == ["om_123"]


def test_ensure_lark_ready_missing_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    # No resolvable lark-cli: no explicit path and LARK_CLI points nowhere.
    monkeypatch.delenv("LARK_CLI", raising=False)
    monkeypatch.setenv("LARK_CLI", "/nonexistent/lark-cli")
    monkeypatch.setenv("A_SHARE_LARK_PREFLIGHT", "1")
    monkeypatch.delenv("A_SHARE_LARK_AUTO_BIND", raising=False)
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_test")

    status = senders._ensure_lark_ready(lark_cli=None, has_targets=True)

    assert status["ok"] is False
    assert status["reason"] == "lark_cli_missing"


def test_ensure_lark_ready_no_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A_SHARE_FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("A_SHARE_FEISHU_USER_ID", raising=False)
    monkeypatch.delenv("FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_USER_ID", raising=False)
    monkeypatch.setenv("A_SHARE_LARK_PREFLIGHT", "1")

    status = senders._ensure_lark_ready(lark_cli="/bin/echo", has_targets=False)

    assert status["ok"] is False
    assert status["reason"] == "no_lark_target"


def test_ensure_lark_ready_disabled_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A_SHARE_LARK_PREFLIGHT", "0")

    status = senders._ensure_lark_ready(lark_cli="/bin/echo", has_targets=False)

    assert status["ok"] is True
    assert status["reason"] == "preflight_disabled"


def test_ensure_lark_ready_ready_without_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, _ = _fake_run(0, stdout='{"identity":"bot","available":true,"tokenStatus":"ready"}')
    monkeypatch.setattr(senders.subprocess, "run", fake)
    monkeypatch.delenv("LARK_CLI", raising=False)
    monkeypatch.setenv("A_SHARE_LARK_PREFLIGHT", "1")
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_test")

    status = senders._ensure_lark_ready(lark_cli="/bin/echo", has_targets=True)

    assert status["ok"] is True
    assert status["reason"] == "ready"
    assert status["bind_attempted"] is False


def test_ensure_lark_ready_rebinds_from_hermes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    whoami_count = {"value": 0}

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": list(cmd), "env": env or {}})
        if cmd[1:] == ["whoami"]:
            whoami_count["value"] += 1
            if whoami_count["value"] == 1:
                return subprocess.CompletedProcess(
                    cmd, 0, '{"identity":"bot","available":false,"tokenStatus":"missing"}', ""
                )
            return subprocess.CompletedProcess(
                cmd, 0, '{"identity":"bot","available":true,"tokenStatus":"ready"}', ""
            )
        if cmd[1:3] == ["config", "bind"]:
            return subprocess.CompletedProcess(cmd, 0, '{"ok":true}', "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(senders.subprocess, "run", fake_run)
    monkeypatch.delenv("LARK_CLI", raising=False)
    monkeypatch.setenv("A_SHARE_LARK_PREFLIGHT", "1")
    monkeypatch.setenv("A_SHARE_LARK_AUTO_BIND", "1")
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_test")

    status = senders._ensure_lark_ready(lark_cli="/bin/echo", has_targets=True)

    assert status["ok"] is True
    assert status["bind_attempted"] is True
    assert status["bind_ok"] is True
    assert status["reason"] == "ready_after_bind"


def test_lark_target_arg_sets_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_one,oc_two")
    monkeypatch.delenv("A_SHARE_FEISHU_USER_ID", raising=False)
    monkeypatch.delenv("FEISHU_USER_ID", raising=False)

    assert _lark_target_arg_sets() == [
        ["--chat-id", "oc_one"],
        ["--chat-id", "oc_two"],
    ]


def test_lark_target_arg_sets_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A_SHARE_FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_CHAT_ID", raising=False)
    monkeypatch.setenv("A_SHARE_FEISHU_USER_ID", "u_one,u_two")

    assert _lark_target_arg_sets() == [
        ["--user-id", "u_one"],
        ["--user-id", "u_two"],
    ]


def test_lark_target_arg_sets_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A_SHARE_FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("A_SHARE_FEISHU_USER_ID", raising=False)
    monkeypatch.delenv("FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_USER_ID", raising=False)

    assert _lark_target_arg_sets() == []


def test_lark_target_arg_sets_explicit_chat_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_env")
    assert _lark_target_arg_sets(chat_id="oc_explicit") == [["--chat-id", "oc_explicit"]]


def test_resolve_delivery_targets_filters_disabled_and_duplicate_audiences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_INTEL_CLIENT_CHAT_ID", "feishu:oc_client,oc_client")
    monkeypatch.setenv("MARKET_INTEL_INTERNAL_CHAT_ID", "oc_internal,oc_client")
    monkeypatch.setenv("MARKET_INTEL_DISABLED_CHAT_ID", "feishu:oc_internal")

    assert resolve_delivery_targets() == {
        "client": ("oc_client",),
        "internal": (),
    }
