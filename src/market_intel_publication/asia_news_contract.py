"""Public projection of independently reviewed Asia news, bound to report bytes."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from zoneinfo import ZoneInfo

from daily_messenger.daily_report.asia_news_contract import (
    MARKET_ZONES,
    aware_timestamp,
    digest,
    required_text,
    secure_source_url,
    validate_asia_candidate,
)
from daily_messenger.daily_report.asia_news_review import _record, validate_asia_review

SCHEMA = "market_intel.asia_news_public.v1"
HASH = re.compile(r"[a-f0-9]{64}")
PRIVATE = re.compile(
    r"/home/|/Users/|\b(?:sk-|ghp_|github_pat_)[\w-]{8,}|\bBearer\s+\S+|(?:api_key|password|secret|token)\s*[:=]",
    re.I,
)


def _public_text(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 2000
        or PRIVATE.search(value)
    ):
        raise ValueError("invalid public news text")
    return value


def _public_item(row: Mapping[str, object], cutoff) -> dict:
    candidate_payload, receipt = row.get("candidate"), row.get("review")
    if not isinstance(candidate_payload, dict) or not isinstance(receipt, dict):
        raise ValueError("candidate and independent review required")
    candidate = validate_asia_candidate(_record(candidate_payload))
    reviewed = validate_asia_review(candidate, _record(receipt), cutoff=cutoff)
    translation = reviewed["translation"]
    english = _record(translation)["text"] if translation is not None else None
    return {
        "evidence_id": candidate.evidence_id,
        "market": candidate.market,
        "source_url": candidate.source_url,
        "publisher": _public_text(candidate.publisher),
        "published_at": candidate.published_at,
        "time_precision": candidate.time_precision,
        "event_date": candidate.event_date,
        "source_sha256": candidate.source_sha256,
        "claim": _public_text(reviewed["claim"]),
        "claim_sha256": reviewed["claim_sha256"],
        "claim_en": _public_text(english) if english is not None else None,
        "claim_en_sha256": digest(english) if english is not None else None,
        "applicability": reviewed["applicability"],
    }


def build_public_asia_news(
    reviewed_items: Sequence[Mapping[str, object]],
    *,
    report_date: str,
    generated_at: str,
    report_sha256: str,
) -> dict:
    """No private receipt or raw body escapes this projection."""
    if date.fromisoformat(report_date).isoformat() != report_date or not HASH.fullmatch(
        report_sha256
    ):
        raise ValueError("invalid report identity")
    cutoff = aware_timestamp(f"{report_date}T19:00:00+08:00")
    generated = aware_timestamp(generated_at)
    if generated < cutoff:
        raise ValueError("generation precedes news cutoff")
    markets: dict[str, list] = {"cn": [], "hk": []}
    seen: set[str] = set()
    for row in reviewed_items:
        receipt = row.get("review")
        if (
            not isinstance(receipt, Mapping)
            or aware_timestamp(required_text(_record(receipt), "reviewed_at")) > generated
        ):
            raise ValueError("review after public generation")
        item = _public_item(row, cutoff)
        if item["evidence_id"] in seen:
            raise ValueError("duplicate public evidence")
        seen.add(item["evidence_id"])
        markets[item["market"]].append(item)
    payload = {
        "schema_version": SCHEMA,
        "publication": "public",
        "report_id": f"{report_date}-evening",
        "date": report_date,
        "kind": "evening",
        "generated_at": generated_at,
        "cutoff": cutoff.isoformat(),
        "report_sha256": report_sha256,
        "status": "reviewed" if seen else "missing",
        "markets": markets,
    }
    payload["content_sha256"] = digest(payload)
    validate_public_asia_news(payload, report_id=payload["report_id"], report_sha256=report_sha256)
    return payload


def _validate_item(item: object, market: str, cutoff) -> None:
    if not isinstance(item, dict) or item.get("market") != market:
        raise ValueError("news market mismatch")
    item = _record(item)
    secure_source_url(required_text(item, "source_url"))
    _public_text(item.get("publisher"))
    if not re.fullmatch(
        r"asia\.[a-f0-9]{64}", required_text(item, "evidence_id")
    ) or not HASH.fullmatch(required_text(item, "source_sha256")):
        raise ValueError("invalid public source identity")
    claim = _public_text(item.get("claim"))
    if item.get("claim_sha256") != digest(claim):
        raise ValueError("public claim hash mismatch")
    english = item.get("claim_en")
    if (english is None and item.get("claim_en_sha256") is not None) or (
        english is not None and digest(_public_text(english)) != item.get("claim_en_sha256")
    ):
        raise ValueError("public translation binding mismatch")
    if item.get("applicability") not in {"eligible", "holiday_context"}:
        raise ValueError("unverified public applicability")
    publication = required_text(item, "published_at")
    if item.get("time_precision") == "timestamp":
        if aware_timestamp(publication) > cutoff:
            raise ValueError("source after cutoff")
    elif item.get("time_precision") == "date":
        if date.fromisoformat(publication) >= cutoff.astimezone(MARKET_ZONES[market]).date():
            raise ValueError("unverified date-only cutoff")
    else:
        raise ValueError("invalid source precision")


def validate_public_asia_news(payload: dict, *, report_id: str, report_sha256: str) -> None:
    """Recheck public identity/integrity. This is not an independent fact review."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-evening", report_id):
        raise ValueError("invalid news report ID")
    if (
        payload.get("schema_version") != SCHEMA
        or payload.get("publication") != "public"
        or payload.get("report_id") != report_id
        or payload.get("date") != report_id[:10]
        or payload.get("kind") != "evening"
        or payload.get("report_sha256") != report_sha256
    ):
        raise ValueError("news report binding mismatch")
    if payload.get("content_sha256") != digest(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    ):
        raise ValueError("public news content hash mismatch")
    cutoff = aware_timestamp(required_text(payload, "cutoff"))
    if (
        cutoff.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()
        != f"{report_id[:10]}T19:00:00+08:00"
        or aware_timestamp(required_text(payload, "generated_at")) < cutoff
    ):
        raise ValueError("invalid public news cutoff")
    markets = payload.get("markets")
    if not isinstance(markets, dict) or set(markets) != {"cn", "hk"}:
        raise ValueError("invalid public news markets")
    ids: set[str] = set()
    for market, items in markets.items():
        if not isinstance(items, list) or len(items) > 10:
            raise ValueError("invalid public news item count")
        for item in items:
            _validate_item(item, market, cutoff)
            if item["evidence_id"] in ids:
                raise ValueError("duplicate public news identity")
            ids.add(item["evidence_id"])
    if payload.get("status") != ("reviewed" if ids else "missing"):
        raise ValueError("public news status mismatch")
