from __future__ import annotations

import json
from pathlib import Path

import pytest

from a_share_analysis.weekly_analysis_artifact import load_weekly_analysis_artifact


def _write(path: Path, artifact_type: str = "value_regime_weekly") -> None:
    payload = {
        "schema_version": "research.weekly_analysis.v1",
        "artifact_type": artifact_type,
        "as_of": "20250502",
        "quality": {"status": "passed", "observation_count": 1},
        "snapshot": {"regime": "MOMENTUM"},
        "weekly_features": [{"date": "20250502", "weekly_return": 0.01}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_weekly_analysis_artifact_validates_owner_contract(tmp_path: Path) -> None:
    path = tmp_path / "value.json"
    _write(path)

    payload = load_weekly_analysis_artifact(
        path, artifact_type="value_regime_weekly", expected_as_of="20250502"
    )

    assert payload["snapshot"]["regime"] == "MOMENTUM"


@pytest.mark.parametrize(
    "artifact_type,overrides",
    [
        ("size_style_weekly", {}),
        ("value_regime_weekly", {"quality": {"status": "unavailable"}}),
        ("value_regime_weekly", {"as_of": "20250501"}),
    ],
)
def test_load_weekly_analysis_artifact_rejects_invalid_payload(
    tmp_path: Path, artifact_type: str, overrides: dict[str, object]
) -> None:
    path = tmp_path / "artifact.json"
    _write(path, artifact_type)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_weekly_analysis_artifact(
            path, artifact_type="value_regime_weekly", expected_as_of="20250502"
        )
