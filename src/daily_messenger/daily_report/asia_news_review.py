"""Independent, exact-content receipts; validation does not establish factual truth."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime

from .asia_news_contract import (
    AsiaNewsCandidate,
    aware_timestamp,
    candidate_applicability,
    digest,
    required_text,
    secure_source_url,
    validate_asia_candidate,
)


def _record(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError("invalid receipt object")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _calendar_status(candidate: AsiaNewsCandidate, calendar: object, cutoff: datetime) -> str:
    calendar = _record(calendar)
    if calendar.get("market") != candidate.market:
        raise ValueError("calendar market mismatch")
    secure_source_url(required_text(calendar, "source_url"))
    if not re.fullmatch(r"[a-f0-9]{64}", required_text(calendar, "source_sha256")):
        raise ValueError("invalid calendar source identity")
    dates = calendar.get("open_dates")
    if not isinstance(dates, list) or not all(isinstance(value, str) for value in dates):
        raise ValueError("invalid calendar sessions")
    return candidate_applicability(
        candidate,
        cutoff=cutoff,
        open_dates=[date.fromisoformat(value) for value in dates if isinstance(value, str)],
        calendar_from=date.fromisoformat(required_text(calendar, "from")),
        calendar_through=date.fromisoformat(required_text(calendar, "through")),
    )


def _independent_identity(receipt: Mapping[str, object], producer: str) -> str:
    reviewer = required_text(receipt, "reviewer")
    if reviewer == producer:
        raise ValueError("producer cannot approve own claim")
    return reviewer


def _translation(
    candidate: AsiaNewsCandidate, review: Mapping[str, object], claim: str
) -> dict | None:
    value = review.get("translation")
    if value is None:
        return None
    value = _record(value)
    text = required_text(value, "text")
    if value.get("sha256") != digest(text) or value.get("claim_sha256") != digest(claim):
        raise ValueError("translation content binding mismatch")
    _independent_identity(value, candidate.collector_identity)
    aware_timestamp(required_text(value, "reviewed_at"))
    required_text(value, "note")

    def numbers(content: str) -> list[str]:
        return sorted(re.findall(r"[-+]?\d+(?:[,.]\d+)*%?", content))

    if numbers(text) != numbers(claim):
        raise ValueError("translation numeric mismatch")
    return dict(value)


def validate_asia_review(
    candidate: AsiaNewsCandidate,
    review: Mapping[str, object],
    *,
    cutoff: datetime,
) -> dict[str, object]:
    """Require separate date, fact, rights and exact bilingual-content attestations."""
    candidate = validate_asia_candidate(asdict(candidate))
    if (
        review.get("schema_version") != "market_intel.asia_news_review.v1"
        or review.get("status") != "approved"
    ):
        raise ValueError("news item is not independently approved")
    _independent_identity(review, candidate.collector_identity)
    reviewed_at = aware_timestamp(required_text(review, "reviewed_at"))
    if reviewed_at < aware_timestamp(candidate.retrieved_at):
        raise ValueError("review precedes source retrieval")
    if aware_timestamp(required_text(review, "cutoff")) != cutoff:
        raise ValueError("review cutoff mismatch")
    bindings = {
        "candidate_sha256": candidate.evidence_id.removeprefix("asia."),
        "source_sha256": candidate.source_sha256,
        "source_url": candidate.source_url,
    }
    if any(review.get(key) != value for key, value in bindings.items()):
        raise ValueError("source or candidate review binding mismatch")
    claim = required_text(review, "claim")
    if review.get("claim_sha256") != digest(claim):
        raise ValueError("approved claim hash mismatch")
    for key in ("source_date_note", "fact_note", "rights_note", "applicability_note"):
        required_text(review, key)
    status = _calendar_status(candidate, review.get("calendar"), cutoff)
    if status not in {"eligible", "holiday_context"}:
        raise ValueError(f"news applicability blocked: {status}")
    return {
        **review,
        "claim": claim,
        "applicability": status,
        "translation": _translation(candidate, review, claim),
    }


def review_template(candidate: AsiaNewsCandidate, *, cutoff: datetime) -> dict[str, object]:
    """Identity-only template with deliberately empty approval attestations."""
    return {
        "schema_version": "market_intel.asia_news_review.v1",
        "status": "needs_review",
        "candidate_sha256": candidate.evidence_id.removeprefix("asia."),
        "source_url": candidate.source_url,
        "source_sha256": candidate.source_sha256,
        "cutoff": cutoff.isoformat(),
        "reviewer": "",
        "reviewed_at": "",
        "claim": "",
        "claim_sha256": "",
        "source_date_note": "",
        "fact_note": "",
        "rights_note": "",
        "applicability_note": "",
        "calendar": None,
    }
