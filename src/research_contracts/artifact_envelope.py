from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

ARTIFACT_ENVELOPE_KEY = "artifact_envelope"
ARTIFACT_ENVELOPE_SCHEMA_VERSION = "research.artifact-envelope.v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
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


@dataclass(frozen=True)
class ProducerIdentity:
    repository: str
    version: str
    commit: str
    backend: str
    backend_version: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.repository, "producer.repository")
        _required_text(self.version, "producer.version")
        _required_text(self.commit, "producer.commit")
        _required_text(self.backend, "producer.backend")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ProducerIdentity:
        backend_version = str(payload.get("backend_version") or "").strip() or None
        return cls(
            repository=_required_text(payload.get("repository"), "producer.repository"),
            version=_required_text(payload.get("version"), "producer.version"),
            commit=_required_text(payload.get("commit"), "producer.commit"),
            backend=_required_text(payload.get("backend"), "producer.backend"),
            backend_version=backend_version,
        )

    def to_mapping(self) -> dict[str, str]:
        result = {
            "repository": self.repository,
            "version": self.version,
            "commit": self.commit,
            "backend": self.backend,
        }
        if self.backend_version is not None:
            result["backend_version"] = self.backend_version
        return result


@dataclass(frozen=True)
class LineageInput:
    artifact_id: str
    sha256: str

    def __post_init__(self) -> None:
        _required_text(self.artifact_id, "lineage.artifact_id")
        _sha256(self.sha256, "lineage.sha256")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> LineageInput:
        return cls(
            artifact_id=_required_text(payload.get("artifact_id"), "lineage.artifact_id"),
            sha256=_sha256(payload.get("sha256"), "lineage.sha256"),
        )

    def to_mapping(self) -> dict[str, str]:
        return {"artifact_id": self.artifact_id, "sha256": self.sha256}


@dataclass(frozen=True)
class TargetHandoffContext:
    valid_from: datetime
    expires_at: datetime
    portfolio_scope: str
    account_scope: str
    policy_reference: str
    idempotency_scope: str

    def __post_init__(self) -> None:
        _aware_datetime(self.valid_from, "target_handoff.valid_from")
        _aware_datetime(self.expires_at, "target_handoff.expires_at")
        if self.expires_at <= self.valid_from:
            raise ValueError("target_handoff.expires_at must be after valid_from")
        _required_text(self.portfolio_scope, "target_handoff.portfolio_scope")
        _required_text(self.account_scope, "target_handoff.account_scope")
        _required_text(self.policy_reference, "target_handoff.policy_reference")
        _required_text(self.idempotency_scope, "target_handoff.idempotency_scope")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TargetHandoffContext:
        valid_from = _aware_datetime(payload.get("valid_from"), "target_handoff.valid_from")
        expires_at = _aware_datetime(payload.get("expires_at"), "target_handoff.expires_at")
        if expires_at <= valid_from:
            raise ValueError("target_handoff.expires_at must be after valid_from")
        return cls(
            valid_from=valid_from,
            expires_at=expires_at,
            portfolio_scope=_required_text(
                payload.get("portfolio_scope"), "target_handoff.portfolio_scope"
            ),
            account_scope=_required_text(
                payload.get("account_scope"), "target_handoff.account_scope"
            ),
            policy_reference=_required_text(
                payload.get("policy_reference"), "target_handoff.policy_reference"
            ),
            idempotency_scope=_required_text(
                payload.get("idempotency_scope"), "target_handoff.idempotency_scope"
            ),
        )

    def to_mapping(self) -> dict[str, str]:
        return {
            "valid_from": self.valid_from.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "portfolio_scope": self.portfolio_scope,
            "account_scope": self.account_scope,
            "policy_reference": self.policy_reference,
            "idempotency_scope": self.idempotency_scope,
        }


@dataclass(frozen=True)
class ArtifactEnvelopeV2:
    artifact_id: str
    artifact_type: str
    run_id: str
    created_at: datetime
    producer: ProducerIdentity
    configuration_sha256: str
    content_sha256: str
    lineage: tuple[LineageInput, ...] = ()
    target_handoff: TargetHandoffContext | None = None
    write_mode: str = "opt_in"
    schema_version: str = ARTIFACT_ENVELOPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
            raise ValueError(f"unsupported artifact envelope schema {self.schema_version!r}")
        if self.write_mode != "opt_in":
            raise ValueError("artifact envelope write_mode must be opt_in")
        _required_text(self.artifact_id, "artifact_id")
        _required_text(self.artifact_type, "artifact_type")
        _required_text(self.run_id, "run_id")
        _aware_datetime(self.created_at, "created_at")
        _sha256(self.configuration_sha256, "configuration_sha256")
        _sha256(self.content_sha256, "content_sha256")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ArtifactEnvelopeV2:
        schema_version = _required_text(payload.get("schema_version"), "schema_version")
        if schema_version != ARTIFACT_ENVELOPE_SCHEMA_VERSION:
            raise ValueError(f"unsupported artifact envelope schema {schema_version!r}")

        producer_payload = payload.get("producer")
        if not isinstance(producer_payload, Mapping):
            raise ValueError("producer must be an object")
        lineage_payload = payload.get("lineage")
        if not isinstance(lineage_payload, list):
            raise ValueError("lineage must be a list")
        lineage = tuple(
            LineageInput.from_mapping(item) for item in lineage_payload if isinstance(item, Mapping)
        )
        if len(lineage) != len(lineage_payload):
            raise ValueError("each lineage item must be an object")

        target_payload = payload.get("target_handoff")
        if target_payload is not None and not isinstance(target_payload, Mapping):
            raise ValueError("target_handoff must be an object")
        target_handoff = (
            TargetHandoffContext.from_mapping(target_payload)
            if isinstance(target_payload, Mapping)
            else None
        )
        return cls(
            schema_version=schema_version,
            artifact_id=_required_text(payload.get("artifact_id"), "artifact_id"),
            artifact_type=_required_text(payload.get("artifact_type"), "artifact_type"),
            run_id=_required_text(payload.get("run_id"), "run_id"),
            created_at=_aware_datetime(payload.get("created_at"), "created_at"),
            producer=ProducerIdentity.from_mapping(producer_payload),
            configuration_sha256=_sha256(
                payload.get("configuration_sha256"), "configuration_sha256"
            ),
            content_sha256=_sha256(payload.get("content_sha256"), "content_sha256"),
            lineage=lineage,
            target_handoff=target_handoff,
            write_mode=payload.get("write_mode", "opt_in"),
        )

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "producer": self.producer.to_mapping(),
            "configuration_sha256": self.configuration_sha256,
            "content_sha256": self.content_sha256,
            "lineage": [item.to_mapping() for item in self.lineage],
            "write_mode": self.write_mode,
        }
        if self.target_handoff is not None:
            result["target_handoff"] = self.target_handoff.to_mapping()
        return result


@dataclass(frozen=True)
class LegacyArtifactMetadata:
    payload: Mapping[str, Any]


def read_artifact_envelope(
    payload: Mapping[str, Any], *, allow_legacy: bool = True
) -> ArtifactEnvelopeV2 | LegacyArtifactMetadata:
    candidate: object
    if payload.get("schema_version") == ARTIFACT_ENVELOPE_SCHEMA_VERSION:
        candidate = payload
    else:
        candidate = payload.get(ARTIFACT_ENVELOPE_KEY)
    if candidate is None:
        if allow_legacy:
            return LegacyArtifactMetadata(dict(payload))
        raise ValueError(f"{ARTIFACT_ENVELOPE_KEY} is required")
    if not isinstance(candidate, Mapping):
        raise ValueError(f"{ARTIFACT_ENVELOPE_KEY} must be an object")
    return ArtifactEnvelopeV2.from_mapping(candidate)


def attach_artifact_envelope_v2(
    legacy_payload: Mapping[str, Any], envelope: ArtifactEnvelopeV2
) -> dict[str, Any]:
    if ARTIFACT_ENVELOPE_KEY in legacy_payload:
        raise ValueError(f"{ARTIFACT_ENVELOPE_KEY} already exists")
    migrated = dict(legacy_payload)
    migrated[ARTIFACT_ENVELOPE_KEY] = envelope.to_mapping()
    return migrated
