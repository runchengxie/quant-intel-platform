"""Offline, append-only news revisions that preserve original market evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from market_intel_publication.us_daily_contract import _public_manifest, _read

from .reviewed_research import ReviewedResearch, load_reviewed_research
from .serialization import content_digest, dumps_json


@dataclass(frozen=True)
class NewsRevisionResult:
    changed: bool
    artifact_path: Path | None
    content_hash: str
    added_claims: int


def _validate_paths(inputs: tuple[Path, ...], output_dir: Path) -> None:
    output = output_dir.resolve()
    for source in inputs[:2]:
        directory = source.resolve().parent
        if (
            output == directory
            or output.is_relative_to(directory)
            or directory.is_relative_to(output)
        ):
            raise ValueError("news revision output overlaps an input directory")
    if any(
        source.resolve() == output or source.resolve().is_relative_to(output)
        for source in inputs[2:]
    ):
        raise ValueError("news revision output overlaps a review file")
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("news revision requires a new output directory")


def _append_research(payload: dict, reviewed: ReviewedResearch) -> int:
    by_id = {item["id"]: item for item in payload.get("events", [])}
    claims_by_id = {key: item for item in payload["claims"] for key in item["evidence_ids"]}
    added = 0
    for event, claim in zip(reviewed.events, reviewed.claims, strict=True):
        event_payload = json.loads(dumps_json(event.to_dict()))
        claim_payload = claim.to_dict()
        if event.id in by_id:
            if by_id[event.id] != event_payload or claims_by_id.get(event.id) != claim_payload:
                raise ValueError("reviewed evidence identity conflict")
            continue
        if event.id in claims_by_id or any(row["id"] == event.id for row in payload["facts"]):
            raise ValueError("reviewed evidence identity conflict")
        payload.setdefault("events", []).append(event_payload)
        payload["claims"].append(claim_payload)
        added += 1
    if added:
        sections = payload.setdefault("sections", [])
        by_key = {section["key"]: section for section in sections}
        for key, identifiers in reviewed.sections.items():
            if not identifiers:
                continue
            key = "movers" if key in {"gainers", "losers"} else key
            if key not in by_key:
                section = {"key": key, "title": key, "facts": [], "claims": []}
                sections.append(section)
                by_key[key] = section
            ids = by_key[key].setdefault("claims", [])
            ids.extend(item for item in identifiers if item not in ids)
    return added


def revise_news(
    input_path: Path,
    manifest_path: Path,
    draft_path: Path,
    review_path: Path,
    output_dir: Path,
    *,
    market_date: str,
    news_cutoff: datetime,
    revised_at: datetime,
) -> NewsRevisionResult:
    """Assemble staged files without loading credentials, models or market providers."""
    _validate_paths((input_path, manifest_path, draft_path, review_path), output_dir)
    if any(
        value.tzinfo is None or value.utcoffset() is None for value in (news_cutoff, revised_at)
    ):
        raise ValueError("revision times must be timezone-aware")
    if news_cutoff > revised_at:
        raise ValueError("news cutoff exceeds revision time")
    payload = _read(input_path)
    _public_manifest(input_path, manifest_path)
    if payload["run_id"] != f"daily-{market_date}":
        raise ValueError("news revision market date mismatch")
    if revised_at < datetime.fromisoformat(payload["generated_at"]):
        raise ValueError("news revision predates original generation")
    reviewed = load_reviewed_research(
        draft_path, review_path, market_date=market_date, as_of=news_cutoff, news_only=True
    )
    result = copy.deepcopy(payload)
    added = _append_research(result, reviewed)
    if not added:
        return NewsRevisionResult(False, None, payload["content_hash"], 0)
    result["schema_version"] = "1.1"
    result["generated_at"] = revised_at.isoformat()
    quality = result.setdefault("quality_summary", {})
    if "news_revision" in quality:
        history = quality.setdefault("news_revision_history", [])
        history.append(quality["news_revision"] | {"result_content_hash": payload["content_hash"]})
    quality["revision"] = "news_only"
    quality["news_revision"] = {
        "input_report_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "previous_content_hash": payload["content_hash"],
        "news_cutoff": news_cutoff.isoformat(),
        "revised_at": revised_at.isoformat(),
    }
    result.setdefault("source_status", {})["research"] = {
        "quality": "reviewed",
        "reason": "source_audited",
    }
    result["missing_sources"] = [
        name for name in result.get("missing_sources", []) if name != "research"
    ]
    result["content_hash"] = content_digest(result)
    serialized = dumps_json(result)
    report_sha = hashlib.sha256(serialized.encode()).hexdigest()
    manifest = dumps_json(
        {
            "schema_version": "1.0",
            "publication": "public",
            "report_file": "daily_report.json",
            "report_sha256": report_sha,
            "content_hash": result["content_hash"],
            "run_id": result["run_id"],
        }
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, text in (("daily_report.json", serialized), ("publication.json", manifest)):
        destination = output_dir / name
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(text)
        destination.chmod(0o600)
    return NewsRevisionResult(True, output_dir / "daily_report.json", result["content_hash"], added)
