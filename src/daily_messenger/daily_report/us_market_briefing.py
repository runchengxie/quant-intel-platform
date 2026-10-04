"""Validate and render reviewed U.S. market briefing publication bundles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ops_common.platform_publication import verify_platform_publication

_BRIEFING_SCHEMA_VERSION = "market.briefing.v1"
_REVIEW_SCHEMA_VERSION = "market.source-review.v1"
_CONSUMER = "market-intel"


@dataclass(frozen=True)
class UsMarketBriefingBundle:
    """Resolved, integrity-checked files from one published briefing run."""

    manifest_path: Path
    producer_repository: str
    producer_commit: str
    run_id: str
    generated_at: str
    audience: str
    briefing: Mapping[str, Any]
    review: Mapping[str, Any]
    artifact_paths: tuple[Path, ...]


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value!r} in {label}")

    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except OSError as exc:
        raise FileNotFoundError(f"cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_validator(filename: str) -> Draft202012Validator:
    schema_path = files("daily_messenger.daily_report").joinpath("schemas", filename)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_schema(payload: dict[str, Any], *, filename: str, label: str) -> None:
    validator = _schema_validator(filename)
    error = next(iter(validator.iter_errors(payload)), None)
    if error is not None:
        location = ".".join(str(part) for part in error.absolute_path)
        suffix = f" at {location}" if location else ""
        raise ValueError(f"invalid {label} schema{suffix}: {error.message}")


def _safe_bundle_file(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    if candidate.parent != root:
        raise ValueError(f"bundle file escapes bundle root: {name}")
    if not candidate.is_file():
        raise FileNotFoundError(f"required bundle file missing: {name}")
    return candidate


def _aware_datetime(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _validate_report_identity(
    briefing: dict[str, Any], evidence: dict[str, Any], *, run_id: str
) -> None:
    briefing_date = briefing["market_date"]
    if date.fromisoformat(briefing_date).isoformat() != briefing_date:
        raise ValueError("briefing market_date must be an ISO date")
    if briefing["market"] != "US":
        raise ValueError("briefing market must be US")
    if briefing["status"] != "validated_draft":
        raise ValueError("briefing status must be validated_draft")
    if briefing["run_id"] != run_id:
        raise ValueError("briefing run_id does not match publication manifest")
    if evidence.get("market") != "US" or evidence.get("market_date") != briefing_date:
        raise ValueError("evidence market/date does not match briefing")


def _validate_review_timing(briefing: dict[str, Any], review: dict[str, Any]) -> None:
    if review["market_date"] != briefing["market_date"]:
        raise ValueError("source review market date does not match briefing")
    if _aware_datetime(review["reviewed_at"], label="reviewed_at") < _aware_datetime(
        briefing["generated_at"], label="generated_at"
    ):
        raise ValueError("source review predates briefing generation")


def _validate_briefing_content(briefing: dict[str, Any]) -> list[str]:
    paragraphs = briefing["paragraphs"]
    if len(paragraphs) != 5:
        raise ValueError("briefing must contain exactly five paragraphs")
    expected_text = "\n\n".join(paragraph["text"] for paragraph in paragraphs)
    if briefing["brief_text"] != expected_text:
        raise ValueError("brief_text differs from paragraph text")
    if not all(
        briefing["quality"][key]
        for key in ("structure_passed", "evidence_links_passed", "editorial_rules_passed")
    ):
        raise ValueError("briefing quality checks did not all pass")
    if briefing["quality"]["errors"]:
        raise ValueError("briefing quality contains errors")

    claim_ids = [claim_id for paragraph in paragraphs for claim_id in paragraph["claim_ids"]]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("briefing contains duplicate final claim IDs")
    return claim_ids


def _validate_claim_approvals(claim_ids: list[str], review: dict[str, Any]) -> None:
    decisions = review["decisions"]
    decision_ids = [decision["claim_id"] for decision in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("source review contains duplicate claim decisions")
    if set(decision_ids) != set(claim_ids):
        raise ValueError("source review decisions do not match final claim IDs")
    if any(decision["status"] != "approved" for decision in decisions):
        raise ValueError("all final claims require approved source decisions")


def _validate_semantics(
    *, briefing: dict[str, Any], review: dict[str, Any], evidence: dict[str, Any], run_id: str
) -> None:
    _validate_report_identity(briefing, evidence, run_id=run_id)
    _validate_review_timing(briefing, review)
    claim_ids = _validate_briefing_content(briefing)
    _validate_claim_approvals(claim_ids, review)


def load_us_market_briefing_bundle(
    manifest_path: str | Path, *, allow_internal: bool = False
) -> UsMarketBriefingBundle:
    """Validate publication identity, file hashes and independent source approval."""
    receipt = verify_platform_publication(
        manifest_path,
        allow_internal=allow_internal,
        consumer=_CONSUMER,
    )
    artifacts = receipt.artifacts
    if len(artifacts) != 2:
        raise ValueError("U.S. briefing publication must target exactly two artifacts")
    by_schema = {artifact.schema_version: artifact for artifact in artifacts}
    if set(by_schema) != {_BRIEFING_SCHEMA_VERSION, _REVIEW_SCHEMA_VERSION}:
        raise ValueError("publication must include one briefing and one source-review artifact")
    briefing_artifact = by_schema[_BRIEFING_SCHEMA_VERSION]
    review_artifact = by_schema[_REVIEW_SCHEMA_VERSION]
    if briefing_artifact.audience != review_artifact.audience:
        raise ValueError("briefing and source review audiences must match")

    root = receipt.manifest_path.parent.resolve()
    briefing_path = briefing_artifact.path.resolve()
    review_path = review_artifact.path.resolve()
    if briefing_path.parent != root or briefing_path.name != "briefing.json":
        raise ValueError("briefing artifact must use the fixed bundle path briefing.json")
    if review_path.parent != root or review_path.name != "review.json":
        raise ValueError("source-review artifact must use the fixed bundle path review.json")

    evidence_path = _safe_bundle_file(root, "evidence.json")
    analysis_path = _safe_bundle_file(root, "analysis.json")
    briefing = _read_object(briefing_path, label="briefing")
    review = _read_object(review_path, label="source review")
    evidence = _read_object(evidence_path, label="evidence")
    if briefing.get("schema_version") != _BRIEFING_SCHEMA_VERSION:
        raise ValueError("unsupported U.S. briefing schema version")
    if review.get("schema_version") != _REVIEW_SCHEMA_VERSION:
        raise ValueError("unsupported U.S. source-review schema version")
    _validate_schema(briefing, filename="market.briefing.v1.json", label=_BRIEFING_SCHEMA_VERSION)
    _validate_schema(review, filename="market.source-review.v1.json", label=_REVIEW_SCHEMA_VERSION)

    expected_hashes = {
        "evidence": evidence_path,
        "analysis": analysis_path,
        "briefing": briefing_path,
    }
    for name, path in expected_hashes.items():
        if _sha256(path) != review["hashes"][name]:
            raise ValueError(f"source review {name} hash does not match bundle file")
    _validate_semantics(
        briefing=briefing,
        review=review,
        evidence=evidence,
        run_id=receipt.run_id,
    )
    return UsMarketBriefingBundle(
        manifest_path=receipt.manifest_path,
        producer_repository=receipt.producer_repository,
        producer_commit=receipt.producer_commit,
        run_id=receipt.run_id,
        generated_at=receipt.generated_at,
        audience=briefing_artifact.audience,
        briefing=MappingProxyType(briefing),
        review=MappingProxyType(review),
        artifact_paths=(briefing_path, review_path, evidence_path, analysis_path),
    )


__all__ = ["UsMarketBriefingBundle", "load_us_market_briefing_bundle"]
