"""Private, review-required research candidates from public web reporting."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SECTIONS = frozenset({"market", "drivers", "macro", "company_news", "gainers", "losers"})
NEW_YORK = ZoneInfo("America/New_York")
FIELDS = (
    "section",
    "title",
    "source_url",
    "published_at",
    "observation_date",
    "summary",
    "supporting_passage",
    "phase",
)


def _reason(row: object, market_date: date, cutoff: datetime) -> str | None:
    if not isinstance(row, dict):
        return "invalid_candidate"
    if row.get("section") not in SECTIONS:
        return "invalid_section"
    if not isinstance(row.get("observation_date"), str) or row["observation_date"] != (
        market_date.isoformat()
    ):
        return "observation_date_mismatch"
    source_url = row.get("source_url")
    if not isinstance(source_url, str):
        return "invalid_source_url"
    parsed_url = urlsplit(source_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        return "invalid_source_url"
    published_at = row.get("published_at")
    if not isinstance(published_at, str):
        return "invalid_published_at"
    try:
        source_time = datetime.fromisoformat(published_at)
    except ValueError:
        return "invalid_published_at"
    if source_time.tzinfo is None or source_time.utcoffset() is None:
        return "invalid_published_at"
    if source_time > cutoff:
        return "source_after_cutoff"
    if row.get("phase") not in {"close", "intraday", "event"}:
        return "invalid_phase"
    market_close = datetime.combine(market_date, time(16), tzinfo=NEW_YORK)
    if row["phase"] == "close" and source_time < market_close:
        return "preclose_source"
    if not isinstance(row.get("title"), str) or not row["title"].strip():
        return "missing_title"
    if not isinstance(row.get("summary"), str) or not row["summary"].strip():
        return "missing_summary"
    if not isinstance(row.get("supporting_passage"), str) or not row[
        "supporting_passage"
    ].strip():
        return "missing_support"
    return None


def validate_candidates(
    payload: object, *, market_date: date, cutoff: datetime
) -> tuple[list[dict[str, str]], list[str]]:
    """Check structural and point-in-time boundaries; accepted rows still need review."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        return [], ["invalid_payload"]
    accepted: list[dict[str, str]] = []
    rejected: list[str] = []
    for index, row in enumerate(payload["candidates"]):
        reason = _reason(row, market_date, cutoff)
        if reason:
            rejected.append(f"candidate[{index}]:{reason}")
            continue
        assert isinstance(row, dict)
        candidate: dict[str, Any] = {field: row[field].strip() for field in FIELDS}
        candidate["review_status"] = "needs_review"
        accepted.append(candidate)
    return accepted, rejected
