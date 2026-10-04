"""Honest publication precision and conservative availability intervals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class PublicationTime:
    precision: str
    source_time: datetime | None
    source_date: str | None
    source_timezone: str | None
    time_role: str
    usage: str


def _calendar_date(value: str | None) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("invalid publication date")
    return date.fromisoformat(value)


def publication_interval(evidence: PublicationTime) -> tuple[datetime, datetime]:
    """Return UTC bounds, never a guessed publication instant for date-only data."""
    if evidence.time_role not in {"publication", "filing_acceptance"}:
        raise ValueError("invalid publication time role")
    if evidence.usage not in {"background", "context"}:
        raise ValueError("invalid publication usage")
    if evidence.precision == "timestamp":
        value = evidence.source_time
        if value is None or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("publication timestamp must be timezone-aware")
        if evidence.source_date is not None or evidence.source_timezone is not None:
            raise ValueError("conflicting publication precision fields")
        instant = value.astimezone(UTC)
        return instant, instant
    if evidence.precision != "date" or evidence.source_time is not None:
        raise ValueError("conflicting publication precision fields")
    if evidence.usage != "background":
        raise ValueError("date-only evidence requires background usage")
    day = _calendar_date(evidence.source_date)
    start = datetime.combine(day, time(), tzinfo=UTC)
    if evidence.source_timezone == "unknown":
        return start - timedelta(hours=14), start + timedelta(days=1, hours=12)
    if not isinstance(evidence.source_timezone, str) or not evidence.source_timezone:
        raise ValueError("publication timezone must be explicit")
    try:
        zone = ZoneInfo(evidence.source_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("invalid publication timezone") from exc
    return (
        datetime.combine(day, time(), tzinfo=zone).astimezone(UTC),
        datetime.combine(day + timedelta(days=1), time(), tzinfo=zone).astimezone(UTC),
    )


def validate_publication_time(
    evidence: PublicationTime, *, market_date: str, cutoff: datetime, section: str
) -> None:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("publication cutoff must be timezone-aware")
    _, end = publication_interval(evidence)
    if end > cutoff:
        raise ValueError("reviewed source after cutoff")
    if evidence.precision == "date":
        if _calendar_date(evidence.source_date) > _calendar_date(market_date):
            raise ValueError("future publication date")
        if section not in {"macro", "company_news"}:
            raise ValueError("date-only evidence is background, not close or mover data")
    if evidence.time_role == "filing_acceptance" and section not in {"macro", "company_news"}:
        raise ValueError("filing acceptance is not original publication or close evidence")


def publication_time_from_candidate(candidate: dict) -> PublicationTime:
    precision = candidate.get("publication_precision", "timestamp")
    value = candidate.get("published_at", candidate.get("source_time"))
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value is not None and not isinstance(value, datetime):
        raise ValueError("invalid publication timestamp")
    evidence = PublicationTime(
        precision,
        value,
        candidate.get("source_date"),
        candidate.get("source_timezone"),
        candidate.get("time_role", "publication"),
        candidate.get("usage", "context"),
    )
    publication_interval(evidence)
    return evidence
