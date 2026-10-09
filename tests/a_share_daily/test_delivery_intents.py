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
    assert not senders._send_lark_markdown(
        "synthetic report", chat_id="synthetic-target", message_ids=[]
    )
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
