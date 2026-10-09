"""Business results, not subprocess exit alone, determine recovery success."""

import json
from datetime import UTC

from ops_common.business_freshness import FreshnessContext, probe_stage
from ops_common.recovery_state import successful_delivery_attempt


def test_actual_recovery_action_checks_artifact_result_before_marking_sent(tmp_path, monkeypatch):
    import subprocess
    from datetime import datetime
    from types import SimpleNamespace

    from ops_common.recovery_actions import attempt_recovery

    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(tmp_path))
    context = FreshnessContext(tmp_path / "release", tmp_path / "data", ("20261009",))
    attempts = []
    spec = SimpleNamespace(key="evening_report", report_kind="evening")

    def fake_owner(command):
        assert command[1:5] == ["evening_report", "20261009", "20261009", "deliver"]
        (tmp_path / "evening_latest.json").write_text(
            json.dumps(
                {
                    "success": False,
                    "trade_date": "20261009",
                    "signal_date": "20261009",
                    "delivery_outcome": "unknown",
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="worker exited", stderr="")

    result, recovered = attempt_recovery(
        spec,
        context=context,
        target_date="20261009",
        signal_date="20261009",
        report_mode="deliver",
        local_now=datetime.now(UTC),
        stage_attempts=attempts,
        runner=fake_owner,
        freshness_probe=probe_stage,
    )
    assert not recovered
    assert result["status"] == "recovery_failed"
    assert not successful_delivery_attempt(attempts, target_date="20261009", report_mode="deliver")


def test_unknown_delivery_cannot_be_successful_recovery():
    attempt = {
        "returncode": 0,
        "target_date": "20261009",
        "report_mode": "deliver",
        "delivery_outcome": "unknown",
    }
    assert not successful_delivery_attempt([attempt], target_date="20261009", report_mode="deliver")


def test_wrong_business_date_and_corrupt_receipt_fail_conservatively(tmp_path, monkeypatch):
    root = tmp_path / "receipts"
    root.mkdir()
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(root))
    receipt = root / "evening_latest.json"
    receipt.write_text(
        json.dumps({"success": True, "trade_date": "20261008", "signal_date": "20261009"}),
        encoding="utf-8",
    )
    context = FreshnessContext(tmp_path / "release", tmp_path / "data", ("20261008", "20261009"))
    result = probe_stage(
        context, stage_key="evening_report", target_date="20261009", signal_date="20261009"
    )
    assert not result.fresh
    assert result.target_date == "20261009"
    assert result.actual_date == "20261008"
    receipt.write_text("{corrupt", encoding="utf-8")
    assert not probe_stage(
        context, stage_key="evening_report", target_date="20261009", signal_date="20261009"
    ).fresh


def test_unknown_receipt_is_not_promoted_by_success_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(tmp_path))
    (tmp_path / "evening_latest.json").write_text(
        json.dumps(
            {
                "success": True,
                "trade_date": "20261009",
                "signal_date": "20261009",
                "delivery_outcome": "unknown",
            }
        ),
        encoding="utf-8",
    )
    context = FreshnessContext(tmp_path, tmp_path / "data", ("20261009",))
    assert not probe_stage(
        context, stage_key="evening_report", target_date="20261009", signal_date="20261009"
    ).fresh
