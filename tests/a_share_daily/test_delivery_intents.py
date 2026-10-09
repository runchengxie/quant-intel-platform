import importlib
from concurrent.futures import ThreadPoolExecutor

import pytest


def store(root):
    return importlib.import_module("a_share_daily.delivery.intents").DeliveryIntentStore(root)


def begin(ledger, key="one"):
    return ledger.begin(key, route="lark-text", target_hash="a" * 64, artifact_sha256="b" * 64)


def test_crash_after_send_blocks_retry_and_explicit_resolution(tmp_path):
    ledger = store(tmp_path)
    assert begin(ledger)
    assert store(tmp_path).outcome("one") == "unknown"
    assert not begin(store(tmp_path))
    with pytest.raises(ValueError, match="evidence"):
        ledger.resolve("one", outcome="not_sent", evidence="")
    ledger.resolve("one", outcome="not_sent", evidence="provider verified absence")
    assert begin(ledger)
    ledger.acknowledge("one", message_ids=["synthetic-id"])
    assert ledger.outcome("one") == "confirmed"
    assert not begin(ledger)


def test_concurrent_exact_retry_only_one_sender_and_conflict_rejected(tmp_path):
    store(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: begin(store(tmp_path)), range(2))) == 1
    with pytest.raises(ValueError, match="identity"):
        store(tmp_path).begin("one", route="hermes", target_hash="a" * 64, artifact_sha256="b" * 64)


def test_each_target_and_artifact_has_independent_confirmation(tmp_path):
    ledger = store(tmp_path)
    assert begin(ledger, "text-target-a")
    ledger.acknowledge("text-target-a", message_ids=[])
    assert begin(ledger, "image-target-a")
    assert begin(ledger, "text-target-b")
    assert not begin(ledger, "text-target-a")
    ledger.resolve(
        "image-target-a", outcome="sent", evidence="provider message screenshot verified"
    )
    assert ledger.outcome("image-target-a") == "confirmed"


def test_real_sender_ack_failure_blocks_duplicate_subprocess(tmp_path, monkeypatch):
    from a_share_daily.delivery import senders

    monkeypatch.setenv("A_SHARE_DELIVERY_INTENT_ROOT", str(tmp_path / "intents"))
    calls = []
    monkeypatch.setattr(senders, "_lark_cli_path", lambda _: "synthetic-cli")
    monkeypatch.setattr(
        senders, "_lark_target_arg_sets", lambda **_: [["--chat-id", "synthetic-target"]]
    )

    def external(*_args, **_kwargs):
        calls.append("sent")
        return True, {"message_id": "synthetic-id"}

    monkeypatch.setattr(senders, "_run_lark_result", external)
    ledger_type = type(store(tmp_path / "intents"))
    original = ledger_type.acknowledge
    monkeypatch.setattr(
        ledger_type,
        "acknowledge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk fault")),
    )
    with pytest.raises(OSError, match="disk fault"):
        senders._send_lark_markdown("synthetic report", chat_id="synthetic-target", message_ids=[])
    monkeypatch.setattr(ledger_type, "acknowledge", original)
    with pytest.raises(senders.UnknownDeliveryError):
        senders._send_lark_markdown("synthetic report", chat_id="synthetic-target", message_ids=[])
    assert calls == ["sent"]


def test_owner_resolution_cli_requires_evidence(tmp_path):
    from a_share_daily.cli import _build_parser, _dispatch

    ledger = store(tmp_path)
    assert begin(ledger)
    args = _build_parser().parse_args(
        [
            "delivery-resolve",
            "--root",
            str(tmp_path),
            "--key",
            "one",
            "--outcome",
            "not_sent",
            "--evidence",
            "provider verified absent",
        ]
    )
    assert _dispatch(args) == 0
    assert begin(ledger)


def test_corrected_content_has_distinct_provider_identity(monkeypatch):
    from a_share_daily.delivery import senders

    monkeypatch.setattr(senders, "_lark_cli_path", lambda _: "synthetic-cli")
    monkeypatch.setattr(senders, "_lark_target_arg_sets", lambda **_: [["--chat-id", "target"]])
    keys = set()
    delivered = []

    def provider(command, **_):
        key = command[command.index("--idempotency-key") + 1]
        if key not in keys:
            delivered.append(command[command.index("--markdown") + 1])
            keys.add(key)
        return True, {"message_id": key}

    monkeypatch.setattr(senders, "_run_lark_result", provider)
    for text in ["original report", "corrected report", "corrected report"]:
        assert senders._send_lark_markdown(
            text, idempotency_scope=("morning", "20261010", "report"), message_ids=[]
        )
    assert delivered == ["original report", "corrected report"]


def test_unknown_morning_send_blocks_auto_fallback_and_writes_unknown(tmp_path, monkeypatch):
    import argparse
    import json

    from a_share_daily.delivery import report_delivery, senders

    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(tmp_path / "receipts"))
    monkeypatch.setattr(senders, "_lark_cli_path", lambda _: "synthetic-cli")
    monkeypatch.setattr(senders, "_lark_target_arg_sets", lambda **_: [["--chat-id", "target"]])
    monkeypatch.setattr(senders, "_ensure_lark_ready", lambda **_: {"ok": True})
    monkeypatch.setattr(senders, "_route_enabled", lambda *_: True)
    sent = []
    monkeypatch.setattr(
        senders,
        "_run_lark_result",
        lambda *_args, **_kwargs: (sent.append("lark") or True, {"message_id": "id"}),
    )
    monkeypatch.setattr(
        senders, "_send_hermes_file", lambda *_args, **_kwargs: sent.append("hermes") or True
    )
    monkeypatch.setattr(
        senders, "_send_webhook_text", lambda *_args, **_kwargs: sent.append("webhook") or True
    )
    context = senders._DeliveryContext(
        "auto", "target", None, "same-target", "hermes", "lark", ["target"], ["same-target"]
    )
    report = tmp_path / "report.md"
    report.write_text("synthetic report")
    kwargs = {
        "args": argparse.Namespace(report=str(report)),
        "context": context,
        "trade_date": "20261010",
        "signal_date": "20261010",
        "text": report.read_text(),
        "chart_paths": [],
        "artifacts": [],
        "mode": "auto",
    }
    ledger_type = type(store(tmp_path / "intents"))
    original = ledger_type.acknowledge
    monkeypatch.setattr(
        ledger_type,
        "acknowledge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("ack fault")),
    )
    assert report_delivery._deliver_morning_routes(**kwargs) == 1
    monkeypatch.setattr(ledger_type, "acknowledge", original)
    assert report_delivery._deliver_morning_routes(**kwargs) == 1
    receipt = json.loads((tmp_path / "receipts/morning_latest.json").read_text())
    assert receipt["delivery_outcome"] == "unknown"
    assert receipt["success"] is False
    assert sent == ["lark"]
