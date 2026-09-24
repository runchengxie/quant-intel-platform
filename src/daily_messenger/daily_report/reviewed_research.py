"""Explicit source-audited web research intake; model drafts never publish directly."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .models import MarketEvent, MarketFact, ResearchClaim

INDEX_IDS = {
    "spx": "S&P 500",
    "dow": "Dow Jones Industrial Average",
    "nasdaq": "Nasdaq Composite",
    "russell2000": "Russell 2000",
}
INDEX_SOURCE_HOSTS = {"abcnews.com", "apnews.com"}
SECTIONS = {"market", "drivers", "macro", "company_news", "gainers", "losers"}


@dataclass(frozen=True)
class ReviewedResearch:
    facts: tuple[MarketFact, ...]
    events: tuple[MarketEvent, ...]
    claims: tuple[ResearchClaim, ...]
    sections: dict[str, tuple[str, ...]]


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
    source_time = datetime.fromisoformat(candidate["published_at"])
    if source_time.tzinfo is None or source_time > as_of:
        raise ValueError("reviewed source after cutoff")
    summary = decision.get("approved_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("approved claim must be independently written")
    event_id = f"reviewed.{index}"
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
        ),
    )


def load_reviewed_research(
    draft_path: Path, review_path: Path, *, market_date: str, as_of: datetime
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
    for decision in decisions:
        status = decision.get("status")
        if status not in {"approved", "deferred", "rejected"} or not decision.get("reason"):
            raise ValueError("invalid review decision")
        if status != "approved":
            continue
        index = decision["index"]
        candidate = candidates[index]
        event, claim, item_facts = _approved_item(
            index,
            decision,
            candidate,
            market_date=market_date,
            as_of=as_of,
        )
        events.append(event)
        claims.append(claim)
        facts.extend(item_facts)
        by_section[candidate["section"]].append(event.id)
    return ReviewedResearch(
        facts=tuple(facts),
        events=tuple(events),
        claims=tuple(claims),
        sections={section: tuple(ids) for section, ids in by_section.items()},
    )
