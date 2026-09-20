"""Validation for evidence-linked research claims."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from .models import MarketEvent, MarketFact
from .research import ResearchBundle


@dataclass(frozen=True)
class ValidationResult:
    errors: list[str]
    warnings: list[str]
    accepted_claims: tuple = ()
    source_coverage: float = 0.0


def validate_research_bundle(
    bundle: ResearchBundle,
    facts: Sequence[MarketFact],
    events: Sequence[MarketEvent],
    as_of: datetime,
) -> ValidationResult:
    known_ids = {fact.id for fact in facts} | {event.id for event in events}
    errors: list[str] = []
    accepted = []
    for claim in bundle.claims:
        for evidence_id in claim.evidence_ids:
            if evidence_id not in known_ids:
                errors.append(f"unknown_evidence:{evidence_id}")
        if any(source_time > as_of for source_time in bundle.source_times):
            errors.append("source_after_cutoff")
            break
        if not claim.sources:
            errors.append("claim_without_source")
        elif all(evidence_id in known_ids for evidence_id in claim.evidence_ids):
            accepted.append(claim)
    total = len(bundle.claims)
    coverage = len(accepted) / total if total else 1.0
    return ValidationResult(
        errors=errors, warnings=[], accepted_claims=tuple(accepted), source_coverage=coverage
    )
