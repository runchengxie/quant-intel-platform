from __future__ import annotations

import json
from pathlib import Path

import pytest

from a_share_analysis.weekly_etf_rotation_artifact import (
    WeeklyEtfRotationArtifactError,
    load_weekly_etf_rotation_artifact,
)


def _write(tmp_path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "schema_version": "weekly_etf_rotation.v2",
        "artifact_type": "weekly_etf_rotation",
        "strategy_id": "weekly_etf_rotation_v1",
        "variant_id": "weekly_etf_rotation_fixed_slots_v1",
        "status": "research_only",
        "research_only": True,
        "eligible_for_live": False,
        "signal_date": "20260821",
        "data_as_of": "20260824",
        "execution_window": "next observed session close after signal_date",
        "positions": [
            {"symbol": "510300", "target_weight": 0.5, "status": "NEW"},
            {"symbol": "511260", "target_weight": 0.5, "status": "NEW"},
        ],
        "trade_delta": [],
        "trade_delta_basis": "no_previous_target",
        "portfolio_diagnostics": {"weight_sum": 1.0},
        "source": {"input_sha256": "a" * 64},
    }
    payload.update(overrides)
    path = tmp_path / "weekly_etf_rotation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_research_artifact_and_exposes_display_context(tmp_path: Path) -> None:
    path = _write(tmp_path)

    artifact = load_weekly_etf_rotation_artifact(path, expected_signal_date="2026-08-21")

    assert artifact.strategy_id == "weekly_etf_rotation_v1"
    assert artifact.variant_id == "weekly_etf_rotation_fixed_slots_v1"
    assert artifact.signal_date == "20260821"
    assert artifact.data_as_of == "20260824"
    assert artifact.positions[0]["target_weight"] == 0.5


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"schema_version": "weekly_etf_rotation.v1"}, "schema"),
        ({"eligible_for_live": True}, "eligible_for_live"),
        ({"research_only": False}, "research_only"),
        ({"strategy_id": "other"}, "strategy_id"),
        (
            {"positions": [{"symbol": "510300", "target_weight": 2.0, "status": "NEW"}]},
            "weight",
        ),
        ({"source": {"input_sha256": "0"}}, "SHA-256"),
        ({"data_as_of": "20260820"}, "data_as_of"),
        ({"trade_delta_basis": "broker_holdings"}, "trade_delta_basis"),
        (
            {"positions": [{"symbol": "999999", "target_weight": 1.0, "status": "NEW"}]},
            "frozen universe",
        ),
        ({"trade_delta": {"symbol": "510300"}}, "trade_delta must be a list"),
        (
            {
                "trade_delta": [
                    {
                        "symbol": "999999",
                        "previous_weight": 0.0,
                        "target_weight": 1.0,
                        "status": "NEW",
                    }
                ]
            },
            "trade_delta",
        ),
    ],
)
def test_rejects_unsafe_or_malformed_artifact(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(WeeklyEtfRotationArtifactError, match=message):
        load_weekly_etf_rotation_artifact(_write(tmp_path, **overrides))


def test_expected_signal_date_mismatch_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(WeeklyEtfRotationArtifactError, match="signal_date"):
        load_weekly_etf_rotation_artifact(_write(tmp_path), expected_signal_date="2026-08-28")
