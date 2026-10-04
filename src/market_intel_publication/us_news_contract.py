"""Publication precision and immutable-parent checks for U.S. news revisions."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, cast

from daily_messenger.daily_report.publication_time import (
    publication_time_from_candidate,
    validate_publication_time,
)

REVISION_FIELDS = ("input_report_sha256", "previous_content_hash", "news_cutoff", "revised_at")


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("invalid news revision timestamp")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("news revision timestamp requires timezone")
    return result


def _revision_metadata(metadata: object) -> dict:
    if not isinstance(metadata, dict) or not set(REVISION_FIELDS).issubset(metadata):
        raise ValueError("news revision metadata missing")
    metadata = cast("dict[str, Any]", metadata)
    for name in REVISION_FIELDS[:2]:
        if not isinstance(metadata[name], str) or not re.fullmatch(r"[0-9a-f]{64}", metadata[name]):
            raise ValueError("invalid news revision lineage digest")
    if _instant(metadata["news_cutoff"]) > _instant(metadata["revised_at"]):
        raise ValueError("news revision cutoff exceeds assembly time")
    return metadata


def _validate_history(quality: dict, head: dict) -> None:
    history = quality.get("news_revision_history", [])
    if not isinstance(history, list):
        raise ValueError("invalid news revision history")
    previous = None
    for item in history:
        metadata = _revision_metadata(item)
        if not isinstance(item.get("result_content_hash"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", item["result_content_hash"]
        ):
            raise ValueError("invalid news revision history digest")
        if previous and (
            metadata["previous_content_hash"] != previous["result_content_hash"]
            or _instant(metadata["revised_at"]) < _instant(previous["revised_at"])
        ):
            raise ValueError("broken news revision chain")
        previous = item
    if previous and (
        head["previous_content_hash"] != previous["result_content_hash"]
        or _instant(head["revised_at"]) < _instant(previous["revised_at"])
    ):
        raise ValueError("broken news revision chain")


def validate_news_payload(payload: dict) -> None:
    """Validate schema1.1 evidence without trusting the revision label."""
    quality = payload.get("quality_summary", {})
    cutoff = _instant(payload["as_of"])
    generated = _instant(payload["generated_at"])
    if generated < cutoff:
        raise ValueError("news revision predates market cutoff")
    if quality.get("revision") == "news_only":
        metadata = _revision_metadata(quality.get("news_revision"))
        if _instant(metadata["revised_at"]) != generated:
            raise ValueError("news revision assembly time mismatch")
        cutoff = _instant(metadata["news_cutoff"])
        _validate_history(quality, metadata)
    identifiers = {row["id"] for row in payload["facts"]}
    for event in payload.get("events", []):
        if "published_at" in event:
            raise ValueError("report event must use canonical source_time")
        if event.get("id") in identifiers:
            raise ValueError("duplicate news evidence identity")
        identifiers.add(event["id"])
        section = str(event.get("event_type", "")).removeprefix("web_").rsplit("_", 1)[0]
        if event.get("publication_precision") == "date" and not str(
            event.get("event_type", "")
        ).endswith("_event"):
            raise ValueError("date-only evidence cannot be close or intraday data")
        validate_publication_time(
            publication_time_from_candidate(event),
            market_date=payload["run_id"].removeprefix("daily-"),
            cutoff=cutoff,
            section=section,
        )
    if any(
        not set(claim.get("evidence_ids", [])).issubset(identifiers) for claim in payload["claims"]
    ):
        raise ValueError("news claim references unavailable evidence")


def validate_news_revision(original: dict, revised: dict, *, original_sha256: str) -> None:
    """Compare complete raw artifacts, not only their public fact projection."""
    metadata = _revision_metadata(revised.get("quality_summary", {}).get("news_revision"))
    if metadata["input_report_sha256"] != original_sha256 or metadata[
        "previous_content_hash"
    ] != original.get("content_hash"):
        raise ValueError("news revision parent mismatch")
    if (
        revised["facts"] != original["facts"]
        or revised["as_of"] != original["as_of"]
        or revised["run_id"] != original["run_id"]
    ):
        raise ValueError("news revision changed market facts or identity")
    if _instant(revised["generated_at"]) < _instant(original["generated_at"]):
        raise ValueError("news revision predates original generation")
    for name in ("claims", "events"):
        before = original.get(name, [])
        if revised.get(name, [])[: len(before)] != before:
            raise ValueError("news revision removed or changed prior evidence")
    old_status = {
        key: value for key, value in original.get("source_status", {}).items() if key != "research"
    }
    new_status = {
        key: value for key, value in revised.get("source_status", {}).items() if key != "research"
    }
    if old_status != new_status:
        raise ValueError("news revision changed non-research status")
    if [key for key in original.get("missing_sources", []) if key != "research"] != [
        key for key in revised.get("missing_sources", []) if key != "research"
    ]:
        raise ValueError("news revision removed non-research gaps")
    by_key = {item["key"]: item for item in revised.get("sections", [])}
    for section in original.get("sections", []):
        target = by_key.get(section["key"], {})
        if (
            target.get("facts", []) != section.get("facts", [])
            or target.get("title") != section.get("title")
            or target.get("claims", [])[: len(section.get("claims", []))]
            != section.get("claims", [])
        ):
            raise ValueError("news revision changed original sections")
    _validate_original_quality(original, revised)


def _validate_original_quality(original: dict, revised: dict) -> None:
    old_quality = original.get("quality_summary", {})
    allowed = {"revision", "news_revision", "news_revision_history", "market_revision"}
    new_quality = revised.get("quality_summary", {})
    market_revision = old_quality.get("market_revision")
    if old_quality.get("revision") in {"historical_backfill", "next_morning_rechecked"}:
        market_revision = old_quality["revision"]
    if new_quality.get("market_revision") != market_revision:
        raise ValueError("news revision changed market-generation provenance")
    if {key: value for key, value in old_quality.items() if key not in allowed} != {
        key: value for key, value in new_quality.items() if key not in allowed
    }:
        raise ValueError("news revision changed original quality")
    history = old_quality.get("news_revision_history", [])
    if old_quality.get("revision") == "news_only":
        history = history + [
            old_quality["news_revision"] | {"result_content_hash": original["content_hash"]}
        ]
    if revised.get("quality_summary", {}).get("news_revision_history", []) != history:
        raise ValueError("news revision changed history")
