"""Public/inter-system publication manifest for research projections.

The manifest deliberately carries only file identities and disclosure metadata.
Research algorithms, data-loading helpers, broker objects, and third-party
framework types remain in their owner repositories.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

PLATFORM_PUBLICATION_SCHEMA_VERSION = "research.platform-publication.v1"
PUBLICATION_AUDIENCES = frozenset({"public", "internal"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _aware_datetime(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _required_text(value, field)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _relative_path(value: object) -> str:
    text = _required_text(value, "relative_path")
    if "\\" in text:
        raise ValueError("relative_path must use POSIX separators")
    path = PurePosixPath(text)
    if path.is_absolute() or text.startswith("/"):
        raise ValueError("relative_path must be relative")
    if not path.parts or path.as_posix() == ".":
        raise ValueError("relative_path must point to a file below the bundle root")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative_path must not contain path traversal")
    return path.as_posix()


def _consumers(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("consumers must be a list")
    consumers = tuple(_required_text(item, "consumers[]") for item in value)
    if not consumers:
        raise ValueError("consumers must not be empty")
    if len(set(consumers)) != len(consumers):
        raise ValueError("consumers must be unique")
    return consumers


@dataclass(frozen=True)
class PlatformPublicationArtifact:
    """One explicitly published projection file.

    ``audience`` is a disclosure boundary, not a hint. Public consumers must
    fail closed when an artifact targeted at them is marked ``internal``.
    """

    artifact_id: str
    relative_path: str
    schema_version: str
    sha256: str
    media_type: str
    audience: str
    consumers: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.artifact_id, "artifact_id")
        object.__setattr__(self, "relative_path", _relative_path(self.relative_path))
        _required_text(self.schema_version, "schema_version")
        _sha256(self.sha256, "sha256")
        _required_text(self.media_type, "media_type")
        if self.audience not in PUBLICATION_AUDIENCES:
            raise ValueError("audience must be one of " + ", ".join(sorted(PUBLICATION_AUDIENCES)))
        object.__setattr__(self, "consumers", _consumers(self.consumers))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PlatformPublicationArtifact:
        return cls(
            artifact_id=_required_text(payload.get("artifact_id"), "artifact_id"),
            relative_path=_relative_path(payload.get("relative_path")),
            schema_version=_required_text(payload.get("schema_version"), "schema_version"),
            sha256=_sha256(payload.get("sha256"), "sha256"),
            media_type=_required_text(payload.get("media_type"), "media_type"),
            audience=_required_text(payload.get("audience"), "audience"),
            consumers=_consumers(payload.get("consumers")),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "relative_path": self.relative_path,
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "media_type": self.media_type,
            "audience": self.audience,
            "consumers": list(self.consumers),
        }


@dataclass(frozen=True)
class PlatformPublicationManifest:
    """Versioned handoff from research owners to presentation/distribution surfaces."""

    generated_at: datetime
    producer_repository: str
    producer_commit: str
    run_id: str
    artifacts: tuple[PlatformPublicationArtifact, ...]
    schema_version: str = PLATFORM_PUBLICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PLATFORM_PUBLICATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported platform publication schema {self.schema_version!r}")
        _aware_datetime(self.generated_at, "generated_at")
        _required_text(self.producer_repository, "producer_repository")
        _required_text(self.producer_commit, "producer_commit")
        _required_text(self.run_id, "run_id")
        if not self.artifacts:
            raise ValueError("artifacts must not be empty")
        ids = [artifact.artifact_id for artifact in self.artifacts]
        paths = [artifact.relative_path for artifact in self.artifacts]
        if len(set(ids)) != len(ids):
            raise ValueError("artifact_id values must be unique")
        if len(set(paths)) != len(paths):
            raise ValueError("relative_path values must be unique")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PlatformPublicationManifest:
        schema_version = _required_text(payload.get("schema_version"), "schema_version")
        if schema_version != PLATFORM_PUBLICATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported platform publication schema {schema_version!r}")
        raw_artifacts = payload.get("artifacts")
        if not isinstance(raw_artifacts, list) or not raw_artifacts:
            raise ValueError("artifacts must be a non-empty list")
        artifacts: list[PlatformPublicationArtifact] = []
        for item in raw_artifacts:
            if not isinstance(item, Mapping):
                raise ValueError("each artifact must be an object")
            artifacts.append(PlatformPublicationArtifact.from_mapping(item))
        return cls(
            schema_version=schema_version,
            generated_at=_aware_datetime(payload.get("generated_at"), "generated_at"),
            producer_repository=_required_text(
                payload.get("producer_repository"), "producer_repository"
            ),
            producer_commit=_required_text(payload.get("producer_commit"), "producer_commit"),
            run_id=_required_text(payload.get("run_id"), "run_id"),
            artifacts=tuple(artifacts),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "producer_repository": self.producer_repository,
            "producer_commit": self.producer_commit,
            "run_id": self.run_id,
            "artifacts": [artifact.to_mapping() for artifact in self.artifacts],
        }

    def for_consumer(
        self, consumer: str, *, allow_internal: bool = False
    ) -> tuple[PlatformPublicationArtifact, ...]:
        consumer_name = _required_text(consumer, "consumer")
        selected = tuple(
            artifact for artifact in self.artifacts if consumer_name in artifact.consumers
        )
        if not allow_internal:
            selected = tuple(artifact for artifact in selected if artifact.audience == "public")
        return selected


def load_platform_publication_manifest(
    payload: Mapping[str, Any],
    *,
    consumer: str | None = None,
    allow_internal: bool = False,
) -> PlatformPublicationManifest:
    """Validate and load a publication manifest.

    When a public consumer is supplied, an internal artifact explicitly aimed
    at that consumer is treated as a publication error instead of being
    silently ignored. This is the fail-closed disclosure firewall used by
    public static surfaces.
    """

    manifest = PlatformPublicationManifest.from_mapping(payload)
    if consumer is None:
        return manifest
    consumer_name = _required_text(consumer, "consumer")
    targeted = [artifact for artifact in manifest.artifacts if consumer_name in artifact.consumers]
    if not allow_internal:
        internal = [
            artifact.artifact_id for artifact in targeted if artifact.audience == "internal"
        ]
        if internal:
            raise ValueError(
                f"internal artifacts cannot be published to {consumer_name}: "
                + ", ".join(sorted(internal))
            )
    return manifest


__all__ = [
    "PLATFORM_PUBLICATION_SCHEMA_VERSION",
    "PUBLICATION_AUDIENCES",
    "PlatformPublicationArtifact",
    "PlatformPublicationManifest",
    "load_platform_publication_manifest",
]
