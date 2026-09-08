from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ops_common.platform_publication import verify_platform_publication
from research_contracts import (
    PlatformPublicationArtifact,
    PlatformPublicationManifest,
    file_sha256,
)


def _write_bundle(root: Path, *, include_internal: bool = False) -> Path:
    public_path = root / "strategies" / "evidence.json"
    public_path.parent.mkdir(parents=True)
    public_path.write_text('{"status":"pass"}', encoding="utf-8")
    artifacts = [
        PlatformPublicationArtifact(
            artifact_id="strategy.evidence",
            relative_path="strategies/evidence.json",
            schema_version="strategy.evidence.v1",
            sha256=file_sha256(public_path),
            media_type="application/json",
            audience="public",
            consumers=("market-intel", "trading-research-dashboard"),
        )
    ]
    if include_internal:
        internal_path = root / "internal" / "operator.json"
        internal_path.parent.mkdir(parents=True)
        internal_path.write_text('{"note":"ops"}', encoding="utf-8")
        artifacts.append(
            PlatformPublicationArtifact(
                artifact_id="operator.note",
                relative_path="internal/operator.json",
                schema_version="operator.note.v1",
                sha256=file_sha256(internal_path),
                media_type="application/json",
                audience="internal",
                consumers=("market-intel",),
            )
        )
    manifest = PlatformPublicationManifest(
        generated_at=datetime(2026, 9, 2, 5, 20, tzinfo=UTC),
        producer_repository="runchengxie/research-workspace",
        producer_commit="abc123",
        run_id="run-1",
        artifacts=tuple(artifacts),
    )
    manifest_path = root / "platform-publication.json"
    manifest_path.write_text(json.dumps(manifest.to_mapping()), encoding="utf-8")
    return manifest_path


def test_market_intel_verifies_declared_artifacts(tmp_path: Path) -> None:
    manifest_path = _write_bundle(tmp_path, include_internal=True)

    receipt = verify_platform_publication(manifest_path, allow_internal=True)

    assert receipt.consumer == "market-intel"
    assert receipt.producer_repository == "runchengxie/research-workspace"
    assert [artifact.artifact_id for artifact in receipt.artifacts] == [
        "strategy.evidence",
        "operator.note",
    ]
    assert all(artifact.path.is_file() for artifact in receipt.artifacts)


def test_market_intel_can_fail_closed_on_internal_projection(tmp_path: Path) -> None:
    manifest_path = _write_bundle(tmp_path, include_internal=True)

    with pytest.raises(ValueError, match="internal"):
        verify_platform_publication(manifest_path, allow_internal=False)


def test_market_intel_rejects_tampered_projection(tmp_path: Path) -> None:
    manifest_path = _write_bundle(tmp_path)
    projection = tmp_path / "strategies" / "evidence.json"
    projection.write_text('{"status":"tampered"}', encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        verify_platform_publication(manifest_path)


def test_production_shaped_daily_watch20_fixture_is_consumable() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "publications" / "daily_watch20"
    manifest_path = fixture_root / "platform-publication.json"

    receipt = verify_platform_publication(manifest_path, allow_internal=True)

    assert receipt.producer_repository == "runchengxie/quant-research"
    assert receipt.run_id == "daily-watch20-fixture-20990102"
    assert [artifact.artifact_id for artifact in receipt.artifacts] == [
        "daily_watch20.watchlist",
        "daily_watch20.selection_receipt",
    ]


def test_production_shaped_daily_watch20_fixture_is_fail_closed_without_opt_in() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "publications" / "daily_watch20"

    with pytest.raises(ValueError, match="internal"):
        verify_platform_publication(
            fixture_root / "platform-publication.json",
            allow_internal=False,
        )
