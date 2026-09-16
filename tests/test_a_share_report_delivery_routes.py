from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from a_share_daily.delivery import io_util, report_delivery, senders, targets
from daily_messenger.tools import post_feishu


def _set_delivery_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(tmp_path / "delivery_state"))
    monkeypatch.setenv("A_SHARE_LARK_PREFLIGHT", "0")


def test_deliver_evening_sends_files_and_absolute_media_via_hermes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n事实内容", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text('{"markets":{}}', encoding="utf-8")
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text('{"cross_market":{}}', encoding="utf-8")
    for _label, filename in io_util.EVENING_CHARTS:
        (out_dir / filename).write_bytes(b"png")

    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "hermes")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id="oc_test",
        user_id=None,
        hermes_target="feishu:oc_test",
        hermes_cli="/bin/echo",
        lark_cli=None,
    )

    assert report_delivery.deliver_evening(args) == 0
    assert len(calls) == 8
    assert all(call[:4] == ["/bin/echo", "send", "--to", "feishu:oc_test"] for call in calls)
    assert all("--file" in call for call in calls[:2])
    media_args = [arg for call in calls[2:] for arg in call if arg.startswith("MEDIA:")]
    assert len(media_args) == 6
    assert all(Path(arg.removeprefix("MEDIA:")).is_absolute() for arg in media_args)


def test_deliver_evening_sends_each_payload_to_multiple_hermes_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n事实内容", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text('{"markets":{}}', encoding="utf-8")
    for filename in ("daily_dashboard.png", "daily_sentiment_chart.png"):
        (out_dir / filename).write_bytes(b"png")
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "charts": {
                    "paths": {
                        "dashboard": str(out_dir / "daily_dashboard.png"),
                        "sentiment": str(out_dir / "daily_sentiment_chart.png"),
                        "moneyflow": None,
                        "topic": None,
                    },
                    "skipped": ["moneyflow", "topic", "us_overnight", "weekly_chart"],
                },
                "cross_market": {},
            }
        ),
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "hermes")
    monkeypatch.setenv("A_SHARE_HERMES_TARGET", "feishu:oc_one,feishu:oc_two;feishu:oc_three")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id=None,
        user_id=None,
        hermes_target=None,
        hermes_cli="/bin/echo",
        lark_cli=None,
    )

    assert report_delivery.deliver_evening(args) == 0
    assert len(calls) == 12
    targets = [call[call.index("--to") + 1] for call in calls]
    assert targets.count("feishu:oc_one") == 4
    assert targets.count("feishu:oc_two") == 4
    assert targets.count("feishu:oc_three") == 4


def test_lark_markdown_sends_to_multiple_chat_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_one,oc_two")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    assert senders._send_lark_markdown("日报", lark_cli="/bin/echo")
    assert [call[call.index("--chat-id") + 1] for call in calls] == ["oc_one", "oc_two"]


def test_hermes_targets_prefer_current_chat_id_over_global_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("A_SHARE_HERMES_TARGET", "feishu:oc_legacy")

    assert targets._hermes_targets(chat_id="oc_internal") == ["feishu:oc_internal"]


def test_lark_preflight_rebinds_from_hermes_when_whoami_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        calls.append({"cmd": cmd, "env": env or {}})
        if (
            cmd[1:] == ["whoami"]
            and len([call for call in calls if call["cmd"][1:] == ["whoami"]]) == 1
        ):
            return subprocess.CompletedProcess(
                cmd,
                0,
                '{"identity":"bot","available":false,"tokenStatus":"missing"}',
                "",
            )
        if cmd[1:] == ["config", "bind", "--source", "hermes", "--identity", "bot-only"]:
            return subprocess.CompletedProcess(cmd, 0, '{"ok":true}', "")
        return subprocess.CompletedProcess(
            cmd,
            0,
            '{"identity":"bot","available":true,"tokenStatus":"ready"}',
            "",
        )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    status = senders._ensure_lark_ready(lark_cli="/bin/lark-cli", has_targets=True)

    assert status["ok"] is True
    assert status["bind_attempted"] is True
    assert status["bind_ok"] is True
    assert status["reason"] == "ready_after_bind"
    bind_call = next(call for call in calls if call["cmd"][1:3] == ["config", "bind"])
    assert bind_call["env"]["HERMES_HOME"] == str(tmp_path / "localappdata" / "hermes")


def test_deliver_morning_records_lark_preflight_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "delivery_state"
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(state_dir))
    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "lark")
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_test")
    report = tmp_path / "morning_report.md"
    report.write_text("# 晨报\n事实内容", encoding="utf-8")

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if cmd[1:] == ["whoami"]:
            return subprocess.CompletedProcess(cmd, 1, "", "not configured")
        if cmd[1:3] == ["config", "bind"]:
            return subprocess.CompletedProcess(cmd, 1, "", "bind failed")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        report=str(report),
        chat_id=None,
        user_id=None,
        hermes_target=None,
        hermes_cli=None,
        lark_cli="/bin/lark-cli",
    )

    assert report_delivery.deliver_morning(args) == 1
    state = json.loads((state_dir / "morning_latest.json").read_text(encoding="utf-8"))
    assert state["success"] is False
    assert state["routes"]["lark_text"] is False
    assert state["routes"]["lark_preflight"]["bind_attempted"] is True
    assert state["routes"]["lark_preflight"]["reason"] == "bind_returned_1"


def test_deliver_evening_falls_back_to_hermes_images_only_when_lark_images_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n事实内容", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text('{"markets":{}}', encoding="utf-8")
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text('{"cross_market":{}}', encoding="utf-8")
    for _label, filename in io_util.EVENING_CHARTS:
        (out_dir / filename).write_bytes(b"png")

    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[1:3] == ["im", "+messages-send"] and "--msg-type" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "lark image upload failed")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "auto")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id="oc_test",
        user_id=None,
        hermes_target="feishu:oc_test",
        hermes_cli="/bin/echo",
        lark_cli="/bin/echo",
    )

    assert report_delivery.deliver_evening(args) == 0
    hermes_calls = [call for call in calls if call[1] == "send"]
    lark_calls = [call for call in calls if call[1] == "im"]
    assert len(lark_calls) == 8
    assert len(hermes_calls) == 6
    assert all("--msg-type" in call and "image" in call for call in lark_calls[2:])
    assert all(any(arg.startswith("MEDIA:") for arg in call) for call in hermes_calls)
    assert not any("--file" in call for call in hermes_calls)


def test_deliver_morning_falls_back_to_webhook_without_lark_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    report = tmp_path / "morning_report.md"
    report.write_text("# 晨报\n事实内容", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_post(argv: list[str] | None = None) -> int:
        assert argv is not None
        calls.append(argv)
        return 0

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "auto")
    monkeypatch.delenv("A_SHARE_HERMES_TARGET", raising=False)
    monkeypatch.delenv("HERMES_SEND_TARGET", raising=False)
    monkeypatch.delenv("A_SHARE_FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("A_SHARE_FEISHU_USER_ID", raising=False)
    monkeypatch.delenv("FEISHU_USER_ID", raising=False)
    monkeypatch.setattr(post_feishu, "run", fake_post)

    args = argparse.Namespace(
        report=str(report),
        chat_id=None,
        user_id=None,
        hermes_target=None,
        hermes_cli=None,
        lark_cli="/bin/echo",
    )

    assert report_delivery.deliver_morning(args) == 0
    assert len(calls) == 1
    assert "--summary" in calls[0]
    assert str(report) in calls[0]
