"""Provider-neutral research job and bundle types."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .models import MarketEvent, MarketFact, ResearchClaim


@dataclass(frozen=True)
class ResearchJob:
    kind: str
    prompt_version: str
    as_of: datetime
    inputs: dict[str, Any]


@dataclass(frozen=True)
class ResearchBundle:
    as_of: datetime
    claims: tuple[ResearchClaim, ...]
    source_times: tuple[datetime, ...]
    provider: str
    model: str | None = None
    attempts: int = 1
    error_code: str | None = None


class ResearchProvider(Protocol):
    name: str

    def generate(self, job: ResearchJob) -> ResearchBundle: ...


@dataclass(frozen=True)
class AppliedResearch:
    facts: list[MarketFact]
    claims: tuple[ResearchClaim, ...]
    warnings: list[str] = field(default_factory=list)


def apply_research_bundle(facts: Sequence[MarketFact], bundle: ResearchBundle) -> AppliedResearch:
    return AppliedResearch(facts=list(facts), claims=bundle.claims)


def run_research_job(
    job: ResearchJob,
    facts: Sequence[MarketFact],
    events: Sequence[MarketEvent],
    provider: ResearchProvider,
) -> ResearchBundle:
    del facts, events
    return provider.generate(job)
