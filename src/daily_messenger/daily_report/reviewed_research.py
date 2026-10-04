"""Explicit source-audited web research intake; model drafts never publish directly."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .models import MarketEvent, MarketFact, ResearchClaim
from .publication_time import publication_time_from_candidate, validate_publication_time

INDEX_IDS = {
    "spx": "S&P 500",
    "dow": "Dow Jones Industrial Average",
    "nasdaq": "Nasdaq Composite",
    "russell2000": "Russell 2000",
}
INDEX_SOURCE_HOSTS = {"abcnews.com", "www-cdn.abcnews.com", "apnews.com"}
SECTIONS = {"market", "drivers", "macro", "company_news", "gainers", "losers"}


@dataclass(frozen=True)
class ReviewedResearch:
    facts: tuple[MarketFact, ...]
    events: tuple[MarketEvent, ...]
    claims: tuple[ResearchClaim, ...]
    sections: dict[str, tuple[str, ...]]
    mover_tickers: tuple[str, ...] = ()
    mover_evidence: tuple[tuple[str, str], ...] = ()


def _index_facts(
    decision: dict,
    candidate: dict,
    *,
    source_url: str,
    source_time: datetime,
    market_date: str,
    as_of: datetime,
) -> list[MarketFact]:
    index_returns = decision.get("index_returns", {})
    if not index_returns:
        return []
    if candidate.get("section") != "market" or candidate.get("phase") != "close":
        raise ValueError("index returns require a reviewed close source")
    if urlsplit(source_url).hostname not in INDEX_SOURCE_HOSTS:
        raise ValueError("index returns require an approved AP source")
    if set(index_returns) != set(INDEX_IDS):
        raise ValueError("incomplete index returns")
    index_evidence = decision.get("index_evidence")
    if not isinstance(index_evidence, dict) or set(index_evidence) != set(INDEX_IDS):
        raise ValueError("each index return needs source evidence")
    facts = []
    for symbol, label in INDEX_IDS.items():
        value = index_returns[symbol]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or abs(value) > 100
        ):
            raise ValueError("invalid index return")
        support = index_evidence[symbol]
        if (
            not isinstance(support, dict)
            or support.get("reported_change") != value
            or not isinstance(support.get("locator"), str)
            or not support["locator"].strip()
        ):
            raise ValueError("index return disagrees with reviewed evidence")
        facts.append(
            MarketFact(
                id=f"index.{symbol}.change_percent",
                metric="daily_return",
                instrument=label,
                value=float(value),
                previous=None,
                change=float(value),
                unit="percent",
                source=urlsplit(source_url).hostname or "",
                source_url=source_url,
                source_time=source_time,
                retrieved_at=as_of,
                quality="reviewed",
                observation_date=market_date,
            )
        )
    return facts


def _approved_item(
    index: int,
    decision: dict,
    candidate: dict,
    *,
    market_date: str,
    as_of: datetime,
    evidence_namespace: str | None = None,
) -> tuple[MarketEvent, ResearchClaim, list[MarketFact]]:
    if candidate.get("review_status") != "needs_review":
        raise ValueError("invalid candidate review state")
    if candidate.get("observation_date") != market_date:
        raise ValueError("candidate observation date mismatch")
    section = candidate.get("section")
    if section not in SECTIONS:
        raise ValueError("invalid reviewed section")
    source_url = candidate.get("source_url")
    if not isinstance(source_url, str):
        raise ValueError("invalid reviewed source URL")
    parsed_url = urlsplit(source_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise ValueError("invalid reviewed source URL")
    evidence = publication_time_from_candidate(candidate)
    validate_publication_time(evidence, market_date=market_date, cutoff=as_of, section=section)
    source_time = evidence.source_time
    if candidate.get("phase") not in {"close", "intraday", "event"}:
        raise ValueError("invalid reviewed phase")
    if evidence.precision == "date" and candidate["phase"] != "event":
        raise ValueError("date-only evidence cannot be close or intraday data")
    if evidence.precision == "date" and any(
        key in decision for key in ("index_returns", "index_evidence", "ticker")
    ):
        raise ValueError("date-only evidence cannot supply quotations")
    summary = decision.get("approved_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("approved claim must be independently written")
    event_id = (
        f"reviewed.{evidence_namespace}.{index}" if evidence_namespace else f"reviewed.{index}"
    )
    metadata = {}
    if evidence_namespace or "publication_precision" in candidate or "time_role" in candidate:
        metadata = {
            "publication_precision": evidence.precision,
            "source_date": evidence.source_date,
            "source_timezone": evidence.source_timezone,
            "time_role": evidence.time_role,
            "usage": evidence.usage,
        }
    event = MarketEvent(
        id=event_id,
        event_type=f"web_{section}_{candidate['phase']}",
        title=candidate["title"],
        actual=summary.strip(),
        previous=None,
        forecast=None,
        revised=None,
        source=parsed_url.hostname or "",
        source_url=source_url,
        source_time=source_time,
        quality="reviewed",
        **metadata,
    )
    claim = ResearchClaim(
        claim=summary.strip(),
        evidence_ids=(event_id,),
        sources=(source_url,),
        confidence="confirmed",
        status="accepted",
        provider="source_audit",
    )
    return (
        event,
        claim,
        _index_facts(
            decision,
            candidate,
            source_url=source_url,
            source_time=source_time,
            market_date=market_date,
            as_of=as_of,
        )
        if source_time is not None
        else [],
    )


def _validate_private_approval(decision: dict, candidate: dict, as_of: datetime) -> None:
    for name in ("source_locator", "verified_facts"):
        value = decision.get(name)
        if not value or not isinstance(value, (str, list)):
            raise ValueError("private source review missing")
        if isinstance(value, list) and any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ValueError("invalid private source review")
    basis = decision.get("display_basis")
    if not isinstance(basis, dict) or any(
        not isinstance(basis.get(key), str) or not basis[key].strip()
        for key in ("basis", "scope", "source_url", "verified_on")
    ):
        raise ValueError("display basis review missing")
    if basis["source_url"] != candidate.get("source_url"):
        raise ValueError("display basis review URL mismatch")
    from datetime import date

    verified_on = date.fromisoformat(basis["verified_on"])
    if verified_on.isoformat() != basis["verified_on"] or verified_on > as_of.date():
        raise ValueError("invalid display basis review date")


def load_reviewed_research(
    draft_path: Path,
    review_path: Path,
    *,
    market_date: str,
    as_of: datetime,
    news_only: bool = False,
) -> ReviewedResearch:
    """Load only individually approved candidates bound to an unchanged private draft."""
    draft_bytes = draft_path.read_bytes()
    draft = json.loads(draft_bytes)
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if draft.get("market_date") != market_date or review.get("market_date") != market_date:
        raise ValueError("review market date mismatch")
    if review.get("draft_sha256") != hashlib.sha256(draft_bytes).hexdigest():
        raise ValueError("review draft hash mismatch")
    if not review.get("reviewer") or not isinstance(review.get("decisions"), list):
        raise ValueError("review provenance missing")
    candidates = draft.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("invalid research draft")
    decisions = review["decisions"]
    if len(decisions) != len(candidates) or {row.get("index") for row in decisions} != set(
        range(len(candidates))
    ):
        raise ValueError("every research candidate requires one review decision")
    facts: list[MarketFact] = []
    events: list[MarketEvent] = []
    claims: list[ResearchClaim] = []
    by_section: dict[str, list[str]] = {section: [] for section in SECTIONS}
    mover_tickers: list[str] = []
    mover_evidence: list[tuple[str, str]] = []
    for decision in decisions:
        if news_only and any(
            key in decision for key in ("index_returns", "index_evidence", "ticker")
        ):
            raise ValueError("news-only review cannot add quote instructions")
        status = decision.get("status")
        if status not in {"approved", "deferred", "rejected"} or not decision.get("reason"):
            raise ValueError("invalid review decision")
        if status != "approved":
            continue
        index = decision["index"]
        candidate = candidates[index]
        if news_only:
            _validate_private_approval(decision, candidate, as_of)
        event, claim, item_facts = _approved_item(
            index,
            decision,
            candidate,
            market_date=market_date,
            as_of=as_of,
            evidence_namespace=hashlib.sha256(draft_bytes).hexdigest() if news_only else None,
        )
        ticker = decision.get("ticker")
        if ticker is not None:
            if (
                candidate["section"] not in {"gainers", "losers"}
                or not isinstance(ticker, str)
                or not re.fullmatch(r"[A-Z]{1,5}", ticker)
            ):
                raise ValueError("reviewed mover ticker is invalid")
            mover_tickers.append(ticker)
            mover_evidence.append((ticker, event.id))
        events.append(event)
        claims.append(claim)
        facts.extend(item_facts)
        by_section[candidate["section"]].append(event.id)
    return ReviewedResearch(
        facts=tuple(facts),
        events=tuple(events),
        claims=tuple(claims),
        sections={section: tuple(ids) for section, ids in by_section.items()},
        mover_tickers=tuple(dict.fromkeys(mover_tickers)),
        mover_evidence=tuple(mover_evidence),
    )
