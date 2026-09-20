"""Versioned models for evidence-linked market reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, ClassVar


@dataclass(frozen=True)
class MarketFact:
    id: str
    metric: str
    instrument: str | None
    value: float | int | str | None
    previous: float | int | str | None
    change: float | int | str | None
    unit: str | None
    source: str
    source_url: str | None
    source_time: datetime
    retrieved_at: datetime
    quality: str

    schema_version: ClassVar[str] = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MarketFact:
        required = (
            "id",
            "metric",
            "instrument",
            "value",
            "previous",
            "change",
            "unit",
            "source",
            "source_url",
            "source_time",
            "retrieved_at",
            "quality",
        )
        missing = [name for name in required if name not in payload]
        if missing:
            raise ValueError(f"missing MarketFact fields: {', '.join(missing)}")
        values = dict(payload)
        for name in ("source_time", "retrieved_at"):
            if isinstance(values[name], str):
                values[name] = datetime.fromisoformat(values[name])
        return cls(**{name: values[name] for name in required})


@dataclass(frozen=True)
class MarketEvent:
    id: str
    event_type: str
    title: str
    actual: str | float | int | None
    previous: str | float | int | None
    forecast: str | float | int | None
    revised: str | float | int | None
    source: str
    source_url: str | None
    source_time: datetime
    quality: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MarketEvent:
        required = (
            "id",
            "event_type",
            "title",
            "actual",
            "previous",
            "forecast",
            "revised",
            "source",
            "source_url",
            "source_time",
            "quality",
        )
        missing = [name for name in required if name not in payload]
        if missing:
            raise ValueError(f"missing MarketEvent fields: {', '.join(missing)}")
        values = dict(payload)
        if isinstance(values["source_time"], str):
            values["source_time"] = datetime.fromisoformat(values["source_time"])
        return cls(**{name: values[name] for name in required})


@dataclass(frozen=True)
class ResearchClaim:
    claim: str
    evidence_ids: tuple[str, ...]
    sources: tuple[str, ...]
    confidence: str
    status: str = "accepted"
    provider: str | None = None
    model: str | None = None
    prompt_hash: str | None = None
    attempts: int = 1
    error_code: str | None = None

    ALLOWED_CONFIDENCE: ClassVar[frozenset[str]] = frozenset(
        {"confirmed", "likely", "possible", "unclear"}
    )

    def __post_init__(self) -> None:
        if self.confidence not in self.ALLOWED_CONFIDENCE:
            raise ValueError(f"unsupported confidence: {self.confidence}")
        if self.attempts < 1:
            raise ValueError("attempts must be positive")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence_ids"] = list(self.evidence_ids)
        result["sources"] = list(self.sources)
        return result

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ResearchClaim:
        values = dict(payload)
        values["evidence_ids"] = tuple(values.get("evidence_ids", ()))
        values["sources"] = tuple(values.get("sources", ()))
        return cls(**values)


@dataclass(frozen=True)
class ReportSection:
    key: str
    title: str
    facts: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "facts": list(self.facts),
            "claims": list(self.claims),
        }


@dataclass(frozen=True)
class DailyReport:
    schema_version: str
    as_of: datetime
    generated_at: datetime
    run_id: str
    sections: tuple[ReportSection, ...] = ()
    facts: tuple[MarketFact, ...] = ()
    events: tuple[MarketEvent, ...] = ()
    claims: tuple[ResearchClaim, ...] = ()
    missing_sources: tuple[str, ...] = ()
    quality_summary: dict[str, Any] = field(default_factory=dict)
    source_status: dict[str, Any] = field(default_factory=dict)
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of": self.as_of,
            "generated_at": self.generated_at,
            "run_id": self.run_id,
            "sections": [section.to_dict() for section in self.sections],
            "facts": [fact.to_dict() for fact in self.facts],
            "events": [event.to_dict() for event in self.events],
            "claims": [claim.to_dict() for claim in self.claims],
            "missing_sources": list(self.missing_sources),
            "quality_summary": self.quality_summary,
            "source_status": self.source_status,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DailyReport:
        for name in ("schema_version", "as_of", "generated_at", "run_id"):
            if name not in payload:
                raise ValueError(f"missing DailyReport field: {name}")
        values = dict(payload)
        for name in ("as_of", "generated_at"):
            if isinstance(values[name], str):
                values[name] = datetime.fromisoformat(values[name])
        values["sections"] = tuple(
            ReportSection(
                key=item["key"],
                title=item["title"],
                facts=tuple(item.get("facts", ())),
                claims=tuple(item.get("claims", ())),
            )
            for item in values.get("sections", ())
        )
        values["facts"] = tuple(MarketFact.from_dict(item) for item in values.get("facts", ()))
        values["events"] = tuple(MarketEvent.from_dict(item) for item in values.get("events", ()))
        values["claims"] = tuple(ResearchClaim.from_dict(item) for item in values.get("claims", ()))
        values["missing_sources"] = tuple(values.get("missing_sources", ()))
        return cls(
            schema_version=values["schema_version"],
            as_of=values["as_of"],
            generated_at=values["generated_at"],
            run_id=values["run_id"],
            sections=values["sections"],
            facts=values["facts"],
            events=values["events"],
            claims=values["claims"],
            missing_sources=values["missing_sources"],
            quality_summary=values.get("quality_summary", {}),
            source_status=values.get("source_status", {}),
            content_hash=values.get("content_hash"),
        )
