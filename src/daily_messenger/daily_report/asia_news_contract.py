"""Versioned candidate identity and source-time applicability, without approval."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

from daily_messenger.common.market_news import AI_NEWS_MARKET_SPECS

MARKET_ZONES = {
    spec.market: spec.timezone for spec in AI_NEWS_MARKET_SPECS if spec.market in {"cn", "hk"}
}


def required_text(payload: Mapping[str, object], key: str, *, maximum: int = 2000) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"invalid {key}")
    return value.strip()


def aware_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp requires timezone")
    return parsed


def digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def secure_source_url(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.port not in {None, 443}
        or host == "localhost"
        or "." not in host
        or re.search(r"(?i)(?:token|password|secret|api_key)=", parsed.query)
    ):
        raise ValueError("invalid source URL")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return value
    raise ValueError("source URL cannot be an IP address")


@dataclass(frozen=True)
class AsiaNewsCandidate:
    schema_version: str
    collector_identity: str
    market: str
    source_url: str
    publisher: str
    published_at: str
    time_precision: str
    retrieved_at: str
    language: str
    title: str
    summary: str
    source_sha256: str
    document_status: str
    event_date: str | None = None
    revision_of: str | None = None

    @property
    def evidence_id(self) -> str:
        return "asia." + digest(asdict(self))


def validate_asia_candidate(payload: Mapping[str, object]) -> AsiaNewsCandidate:
    """Reject unbound source identity or manufactured timestamps."""
    keys = (
        "schema_version",
        "collector_identity",
        "market",
        "source_url",
        "publisher",
        "published_at",
        "time_precision",
        "retrieved_at",
        "language",
        "title",
        "summary",
        "source_sha256",
        "document_status",
    )
    values = {key: required_text(payload, key) for key in keys}
    if (
        values["schema_version"] != "market_intel.asia_news_candidate.v1"
        or values["market"] not in MARKET_ZONES
    ):
        raise ValueError("invalid candidate schema or market")
    secure_source_url(values["source_url"])
    if not re.fullmatch(r"[a-f0-9]{64}", values["source_sha256"]):
        raise ValueError("invalid source hash")
    retrieved = aware_timestamp(values["retrieved_at"])
    published = values["published_at"]
    if values["time_precision"] == "timestamp":
        if aware_timestamp(published) > retrieved:
            raise ValueError("publication after retrieval")
    elif values["time_precision"] == "date":
        if date.fromisoformat(published).isoformat() != published:
            raise ValueError("invalid publication date")
        if (
            date.fromisoformat(published)
            > retrieved.astimezone(MARKET_ZONES[values["market"]]).date()
        ):
            raise ValueError("publication after retrieval")
    else:
        raise ValueError("invalid source time precision")
    if values["document_status"] not in {"active", "revised", "cancelled"}:
        raise ValueError("invalid document status")
    event_date, revision = payload.get("event_date"), payload.get("revision_of")
    if event_date is not None:
        if (
            not isinstance(event_date, str)
            or date.fromisoformat(event_date).isoformat() != event_date
        ):
            raise ValueError("invalid event date")
    if revision is not None and (
        not isinstance(revision, str) or not re.fullmatch(r"asia\.[a-f0-9]{64}", revision)
    ):
        raise ValueError("invalid revision identity")
    if values["document_status"] == "revised" and revision is None:
        raise ValueError("revised document requires original identity")
    values["retrieved_at"] = retrieved.astimezone(timezone.utc).isoformat()
    return AsiaNewsCandidate(**values, event_date=event_date, revision_of=revision)


def candidate_applicability(
    candidate: AsiaNewsCandidate,
    *,
    cutoff: datetime,
    open_dates: Sequence[date],
    calendar_from: date,
    calendar_through: date,
) -> str:
    """Classify against the named market's externally supplied calendar coverage."""
    if cutoff.tzinfo is None:
        raise ValueError("cutoff requires timezone")
    if candidate.document_status == "cancelled":
        return "cancelled"
    zone = MARKET_ZONES[candidate.market]
    cutoff_day = cutoff.astimezone(zone).date()
    precise = candidate.time_precision == "timestamp"
    source_day = (
        aware_timestamp(candidate.published_at).astimezone(zone).date()
        if precise
        else date.fromisoformat(candidate.published_at)
    )
    if source_day > cutoff_day or (precise and aware_timestamp(candidate.published_at) > cutoff):
        return "after_cutoff"
    if not calendar_from <= source_day <= cutoff_day <= calendar_through:
        return "calendar_unverified"
    if not precise and source_day == cutoff_day:
        return "time_unverified"
    if source_day not in open_dates:
        return "holiday_context"
    return "eligible"
