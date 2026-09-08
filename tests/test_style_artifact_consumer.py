from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from a_share_analysis.style_analysis import (
    REQUIRED_STYLE_FILES,
    consume_style_artifact,
    resolve_style_artifact,
)
from research_contracts import (
    ArtifactEnvelopeV2,
    ProducerIdentity,
    build_file_receipts,
    file_receipt_payload,
)


def _publish_fixture(data_root: Path, version: str = "20260730-test") -> Path:
    root = data_root / "strategy_outputs" / "style-factors" / version
    root.mkdir(parents=True)
    for name in REQUIRED_STYLE_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name}\n", encoding="utf-8")
    receipts = file_receipt_payload(
        build_file_receipts(root, [root / name for name in REQUIRED_STYLE_FILES])
    )
    envelope = ArtifactEnvelopeV2(
        artifact_id=f"style-factors:{version}",
        artifact_type="style_factor_analysis",
        run_id=version,
        created_at=datetime.now(UTC),
        producer=ProducerIdentity(
            repository="research-workspace",
            version="0.1.0",
            commit="test",
            backend="style_factors",
        ),
        configuration_sha256="a" * 64,
        content_sha256=str(receipts["inventory_sha256"]),
    )
    manifest = {
        "schema_version": "research.style-factors.v1",
        "out_name": version,
        "artifact_envelope": envelope.to_mapping(),
        "file_receipts": receipts,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root.parent / "latest.txt").write_text(f"{version}\n", encoding="utf-8")
    return root


def test_style_consumer_validates_and_copies_owner_artifact(tmp_path: Path) -> None:
    source = _publish_fixture(tmp_path / "data")
    artifact = resolve_style_artifact(tmp_path / "data")

    destination = consume_style_artifact(artifact, tmp_path / "rendered")

    assert artifact.root == source
    assert (destination / "style_analysis_report.md").is_file()
    receipt = json.loads((destination / "consumption_receipt.json").read_text(encoding="utf-8"))
    assert receipt["source_artifact_id"] == "style-factors:20260730-test"


def test_style_consumer_rejects_mutated_owner_artifact(tmp_path: Path) -> None:
    source = _publish_fixture(tmp_path / "data")
    (source / "factor_summary.json").write_text("mutated\n", encoding="utf-8")

    try:
        resolve_style_artifact(tmp_path / "data")
    except ValueError as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("mutated artifact should be rejected")


def test_style_consumer_force_refuses_unrecognized_directory(tmp_path: Path) -> None:
    _publish_fixture(tmp_path / "data")
    artifact = resolve_style_artifact(tmp_path / "data")
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("user data\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unrecognized output directory"):
        consume_style_artifact(artifact, destination, force=True)

    assert marker.read_text(encoding="utf-8") == "user data\n"
