"""Offline delivery evidence and recovery contract."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from a_share_daily.weekly_client_basket_delivery import send_basket_report


def send(tmp_path: Path, **extra):
    args = {
        "report_date": "20260914",
        "target_id": "ou_owner",
        "target_kind": "personal",
        "lark_cli": "lark-cli",
        "receipt_path": tmp_path / "receipt.json",
        "sender_scope": "declared-app",
        "delivery_state_root": tmp_path / "state",
        "legacy_receipt_root": tmp_path / "legacy",
    }
    args.update(extra)
    return send_basket_report("# original", **args)


def test_strict_response_and_no_retry(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: calls.append(a) or subprocess.CompletedProcess([], 0, "{}", "private"),
    )
    assert send(tmp_path).status == "failed"
    assert send(tmp_path).text_state == "uncertain"
    assert len(calls) == 1


def test_week_slot_survives_date_and_path_change(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: (
            calls.append(a)
            or subprocess.CompletedProcess([], 0, '{"ok":true,"data":{"message_id":"om_text"}}', "")
        ),
    )
    assert send(tmp_path).status == "sent"
    held = send(tmp_path, report_date="20260915", receipt_path=tmp_path / "other.json")
    assert held.status == "failed"
    assert held.hold_reason == "identity_conflict"
    assert len(calls) == 1


def test_dry_run_never_overwrites_history(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text("historical")
    assert send(tmp_path, dry_run=True).status == "dry_run"
    assert path.read_text() == "historical"
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize(
    "payload",
    [
        "null",
        "[]",
        '{"ok":"true","data":{"message_id":"om_x"}}',
        '{"ok":true,"data":{"message_id":""}}',
    ],
)
def test_bad_success_envelopes_hold(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, payload, "")
    )
    result = send(tmp_path)
    assert result.text_state == "uncertain"
    assert "ou_owner" not in json.dumps(result.public_projection())


def test_inflight_checkpoint_failure_prevents_transport(tmp_path, monkeypatch):
    import a_share_daily.weekly_client_basket_delivery as delivery

    original = delivery._checkpoint

    def fail_inflight(path, record):
        if record["phases"]["text"]["state"] == "inflight":
            raise OSError("disk full")
        original(path, record)

    monkeypatch.setattr(delivery, "_checkpoint", fail_inflight)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("no durable intent"))
    with pytest.raises(OSError, match="disk full"):
        send(tmp_path)


def test_result_checkpoint_failure_retains_inflight(tmp_path, monkeypatch):
    import a_share_daily.weekly_client_basket_delivery as delivery

    original = delivery._checkpoint
    calls = []

    def fail_result(path, record):
        if record["phases"]["text"]["state"] == "accepted":
            raise OSError("disk full")
        original(path, record)

    monkeypatch.setattr(delivery, "_checkpoint", fail_result)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: (
            calls.append(a)
            or subprocess.CompletedProcess([], 0, '{"ok":true,"data":{"message_id":"om_x"}}', "")
        ),
    )
    with pytest.raises(OSError):
        send(tmp_path)
    monkeypatch.setattr(delivery, "_checkpoint", original)
    assert send(tmp_path).text_state == "inflight"
    assert len(calls) == 1


def test_sender_mismatch_does_not_create_second_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            [], 0, '{"ok":true,"data":{"message_id":"om_x"}}', ""
        ),
    )
    assert send(tmp_path).status == "sent"
    assert send(tmp_path, sender_scope="other-app").hold_reason == "identity_conflict"
    assert len(list((tmp_path / "state").rglob("receipt.json"))) == 1


def image_request(tmp_path):
    import hashlib

    image = tmp_path / "source.png"
    image.write_bytes(b"original png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "weekly_basket.render.v1",
                "report_date": "20260914",
                "artifact_sha256": "a" * 64,
                "files": {
                    "markdown": {"sha256": hashlib.sha256(b"# original").hexdigest(), "size": 10},
                    "png": {
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        "size": image.stat().st_size,
                    },
                },
            }
        )
    )
    return {"image_path": image, "render_manifest_path": manifest}


def test_snapshot_survives_source_change_and_detects_postsend_tamper(tmp_path, monkeypatch):
    args = image_request(tmp_path)
    calls = []

    def transport(command, **kwargs):
        calls.append(command)
        if "--markdown" in command:
            args["image_path"].write_bytes(b"source changed")
        else:
            frozen = kwargs["cwd"] / "report.png"
            assert frozen.read_bytes() == b"original png"
            frozen.chmod(0o600)
            frozen.write_bytes(b"tampered")
        return subprocess.CompletedProcess([], 0, '{"ok":true,"data":{"message_id":"om_x"}}', "")

    monkeypatch.setattr(subprocess, "run", transport)
    result = send(tmp_path, **args)
    assert result.text_state == "accepted"
    assert result.image_state == "uncertain"
    record = json.loads(next((tmp_path / "state").rglob("receipt.json")).read_text())
    assert record["phases"]["image"]["message_id"] == "om_x"
    assert send(tmp_path, **args).hold_reason == "payload_conflict"
    assert len(calls) == 2


def test_image_only_recovery_uses_original_snapshot(tmp_path, monkeypatch):
    args = image_request(tmp_path)

    def crash_after_text(command, **kwargs):
        if "--image" in command:
            raise KeyboardInterrupt
        return subprocess.CompletedProcess([], 0, '{"ok":true,"data":{"message_id":"om_text"}}', "")

    # Crash before image's inflight checkpoint, leaving a legitimate image-only recovery.
    import a_share_daily.weekly_client_basket_delivery as delivery

    original = delivery._advance

    def stop_before_image(slot, path, record, phase, cli):
        if phase == "image":
            raise KeyboardInterrupt
        original(slot, path, record, phase, cli)

    monkeypatch.setattr(delivery, "_advance", stop_before_image)
    monkeypatch.setattr(subprocess, "run", crash_after_text)
    with pytest.raises(KeyboardInterrupt):
        send(tmp_path, **args)
    args["image_path"].write_bytes(b"new source")
    calls = []
    monkeypatch.setattr(delivery, "_advance", original)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: (
            calls.append(command)
            or subprocess.CompletedProcess(
                [], 0, '{"ok":true,"data":{"message_id":"om_image"}}', ""
            )
        ),
    )
    assert send(tmp_path, **args).status == "sent"
    assert len(calls) == 1 and "--image" in calls[0]


def _concurrent_send(root, calls):
    import time

    def transport(*args, **kwargs):
        with calls.open("a") as stream:
            stream.write("called\n")
        time.sleep(0.1)
        return subprocess.CompletedProcess([], 0, '{"ok":true,"data":{"message_id":"om_one"}}', "")

    subprocess.run = transport
    assert send(root).status == "sent"


def test_two_processes_share_one_weekly_transaction(tmp_path):
    import multiprocessing

    context = multiprocessing.get_context("fork")
    calls = tmp_path / "calls.txt"
    workers = [context.Process(target=_concurrent_send, args=(tmp_path, calls)) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
        assert worker.exitcode == 0
    assert calls.read_text().splitlines() == ["called"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["phases"]["text"].update(state="not_started"),
        lambda r: r["phases"]["image"].update(state="accepted", message_id="om_image"),
        lambda r: r["identity"].update(image_required=True),
    ],
)
def test_inconsistent_evidence_never_replays(tmp_path, monkeypatch, mutate):
    from a_share_daily.weekly_client_basket_delivery import WeeklyBasketDeliveryError

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            [], 0, '{"ok":true,"data":{"message_id":"om_x"}}', ""
        ),
    )
    send(tmp_path)
    path = next((tmp_path / "state").rglob("receipt.json"))
    record = json.loads(path.read_text())
    mutate(record)
    path.write_text(json.dumps(record))
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("invalid receipt must not replay")
    )
    with pytest.raises(WeeklyBasketDeliveryError):
        send(tmp_path)


def test_exact_crlf_markdown_is_transported(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: (
            calls.append(command)
            or subprocess.CompletedProcess([], 0, '{"ok":true,"data":{"message_id":"om_crlf"}}', "")
        ),
    )
    from a_share_daily.weekly_client_basket_delivery import send_basket_report

    markdown = "# heading\r\nexact bytes\r\n"
    result = send_basket_report(
        markdown,
        report_date="20260914",
        target_id="ou_owner",
        target_kind="personal",
        lark_cli="fake",
        receipt_path=tmp_path / "legacy.json",
        sender_scope="app",
        delivery_state_root=tmp_path / "state",
        legacy_receipt_root=tmp_path / "legacy",
    )
    assert result.status == "sent"
    assert calls[0][calls[0].index("--markdown") + 1] == markdown


def test_manifest_image_size_conflict_prevents_any_send(tmp_path, monkeypatch):
    from a_share_daily.weekly_client_basket_delivery import WeeklyBasketDeliveryError

    args = image_request(tmp_path)
    manifest = json.loads(args["render_manifest_path"].read_text())
    manifest["files"]["png"]["size"] += 1
    args["render_manifest_path"].write_text(json.dumps(manifest))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("manifest conflict"))
    with pytest.raises(WeeklyBasketDeliveryError, match="hash mismatch"):
        send(tmp_path, **args)


@pytest.mark.parametrize("status", ["sent", "failed", "dry_run"])
def test_legacy_status_readonly_hold_even_partial(tmp_path, monkeypatch, status):
    import hashlib

    from a_share_daily.weekly_client_basket_delivery import idempotency_key

    legacy = tmp_path / "legacy" / "20260914" / "delivery" / "personal.json"
    legacy.parent.mkdir(parents=True)
    raw = json.dumps(
        {
            "status": status,
            "report_date": "20260914",
            "chat_id": "ou_owner",
            "idempotency_key": idempotency_key("ou_owner", "20260914", ""),
            "markdown_sha256": hashlib.sha256(b"# original").hexdigest(),
            "image_status": "failed",
        }
    )
    legacy.write_text(raw)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("legacy must not send"))
    assert send(tmp_path).verification_level == "legacy_unverified"
    assert legacy.read_text() == raw
    assert not list((tmp_path / "state").rglob("receipt.json"))
