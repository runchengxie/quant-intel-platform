"""Consume versioned research-platform publication bundles without source imports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from research_contracts import file_sha256, load_platform_publication_manifest


@dataclass(frozen=True)
class ConsumedPublicationArtifact:
    artifact_id: str
    schema_version: str
    audience: str
    path: Path


@dataclass(frozen=True)
class PlatformPublicationReceipt:
    consumer: str
    producer_repository: str
    producer_commit: str
    run_id: str
    generated_at: str
    manifest_path: Path
    artifacts: tuple[ConsumedPublicationArtifact, ...]


def verify_platform_publication(
    manifest_path: str | Path,
    *,
    allow_internal: bool = False,
    consumer: str = "market-intel",
) -> PlatformPublicationReceipt:
    """Validate and resolve one research-platform publication manifest.

    Only files explicitly targeted at ``consumer`` are returned. Hashes are
    verified before any caller renders or delivers the projection. Internal
    projections require an explicit ``allow_internal=True`` opt-in.
    """

    path = Path(manifest_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"platform publication manifest not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid platform publication JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("platform publication manifest must be a JSON object")

    manifest = load_platform_publication_manifest(
        payload,
        consumer=consumer,
        allow_internal=allow_internal,
    )
    root = path.parent.resolve()
    consumed: list[ConsumedPublicationArtifact] = []
    for artifact in manifest.for_consumer(consumer, allow_internal=allow_internal):
        candidate = (root / artifact.relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(
                f"platform publication artifact escapes bundle root: {artifact.artifact_id}"
            )
        if not candidate.is_file():
            raise FileNotFoundError(
                f"platform publication artifact missing: {artifact.artifact_id} -> {candidate}"
            )
        actual_sha256 = file_sha256(candidate)
        if actual_sha256 != artifact.sha256:
            raise ValueError(
                "platform publication SHA-256 mismatch for "
                f"{artifact.artifact_id}: expected {artifact.sha256}, got {actual_sha256}"
            )
        consumed.append(
            ConsumedPublicationArtifact(
                artifact_id=artifact.artifact_id,
                schema_version=artifact.schema_version,
                audience=artifact.audience,
                path=candidate,
            )
        )

    return PlatformPublicationReceipt(
        consumer=consumer,
        producer_repository=manifest.producer_repository,
        producer_commit=manifest.producer_commit,
        run_id=manifest.run_id,
        generated_at=manifest.generated_at.isoformat(),
        manifest_path=path,
        artifacts=tuple(consumed),
    )


__all__ = [
    "ConsumedPublicationArtifact",
    "PlatformPublicationReceipt",
    "verify_platform_publication",
]
