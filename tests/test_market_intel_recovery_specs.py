from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ops_common.business_freshness import BusinessTargets, FreshnessContext
from ops_common.market_intel_recovery import MARKET_INTEL_SPECS
from ops_common.scheduled_recovery import (
    DEFAULT_SPECS,
    RecoverySpec,
    _build_alert,
    _disabled_stage_statuses,
    reconcile,
)


def test_market_intel_recovery_excludes_research_factor_pipeline() -> None:
    keys = {spec.key for spec in MARKET_INTEL_SPECS}
    assert "factor_pipeline" not in keys
    assert "factor_pipeline" not in {spec.key for spec in DEFAULT_SPECS}
    assert {"daily_market", "current_contract", "morning_model", "morning_report"} <= keys


def test_disabling_morning_model_disables_dependent_morning_report() -> None:
    statuses = _disabled_stage_statuses(DEFAULT_SPECS, ("morning_model",))

    assert statuses == {
        "morning_model": "disabled_by_configuration",
        "morning_report": "disabled_dependency",
    }


def test_failed_recovery_alert_is_retried_for_same_failure(tmp_path: Path) -> None:
    messages: list[str] = []

    def notify(message: str) -> bool:
        messages.append(message)
        return True

    alert = _build_alert(
        previous={"failure_fingerprint": "same", "alert": {"status": "failed"}},
        stages=[{"key": "current_contract", "status": "recovery_failed"}],
        failure_fingerprint="same",
        date_key="20260928",
        state_path=tmp_path / "state.json",
        notifier=notify,
    )

    assert alert["status"] == "sent"
    assert len(messages) == 1


def test_sent_recovery_alert_is_suppressed_for_same_failure(tmp_path: Path) -> None:
    alert = _build_alert(
        previous={"failure_fingerprint": "same", "alert": {"status": "sent"}},
        stages=[{"key": "current_contract", "status": "recovery_failed"}],
        failure_fingerprint="same",
        date_key="20260928",
        state_path=tmp_path / "state.json",
        notifier=lambda _message: (_ for _ in ()).throw(AssertionError("must not send")),
    )

    assert alert["status"] == "suppressed_duplicate"
    assert alert["delivered"] is True

    again = _build_alert(
        previous={"failure_fingerprint": "same", "alert": alert},
        stages=[{"key": "current_contract", "status": "recovery_failed"}],
        failure_fingerprint="same",
        date_key="20260928",
        state_path=tmp_path / "state.json",
        notifier=lambda _message: (_ for _ in ()).throw(AssertionError("must not send")),
    )
    assert again["status"] == "suppressed_duplicate"


def test_legacy_suppression_without_delivery_does_not_hide_failure(tmp_path: Path) -> None:
    alert = _build_alert(
        previous={"failure_fingerprint": "same", "alert": {"status": "suppressed_duplicate"}},
        stages=[{"key": "current_contract", "status": "recovery_failed"}],
        failure_fingerprint="same",
        date_key="20260928",
        state_path=tmp_path / "state.json",
        notifier=lambda _message: True,
    )
    assert alert["status"] == "sent"


def test_reconcile_skips_disabled_stage_and_its_dependents(tmp_path: Path) -> None:
    specs = (
        RecoverySpec("morning_model", "model", "model.timer", "model.service"),
        RecoverySpec(
            "morning_report",
            "report",
            "report.timer",
            "report.service",
            dependencies=("morning_model",),
        ),
    )
    targets = BusinessTargets(
        signal_date="20260916",
        signal_is_open=True,
        previous_open_date="20260915",
        eod_date="20260915",
        minute_date="20260916",
        report_data_date="20260915",
    )

    status, receipt = reconcile(
        now=datetime(2026, 9, 16, 1, tzinfo=UTC),
        state_root=tmp_path / "state",
        repair=True,
        context=FreshnessContext(tmp_path, tmp_path, ()),
        targets=targets,
        specs=specs,
        disabled_stages=("morning_model",),
        runner=lambda _command: (_ for _ in ()).throw(AssertionError("must not run")),
        freshness_probe=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not probe")
        ),
    )

    assert status == 0
    assert receipt["success"] is True
    assert [stage["status"] for stage in receipt["stages"]] == [
        "disabled_by_configuration",
        "disabled_dependency",
    ]
