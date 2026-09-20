from datetime import UTC, datetime, timedelta

from daily_messenger.daily_report.models import MarketFact
from daily_messenger.daily_report.research import (
    ResearchBundle,
    ResearchClaim,
    apply_research_bundle,
)
from daily_messenger.daily_report.validation import validate_research_bundle

AS_OF = datetime(2026, 9, 19, 1, tzinfo=UTC)
FACT = MarketFact(
    id="index.spx.change_percent",
    metric="index_return",
    instrument="SPX",
    value=0.16,
    previous=0.0,
    change=0.16,
    unit="percent",
    source="quotes",
    source_url=None,
    source_time=AS_OF,
    retrieved_at=AS_OF,
    quality="ok",
)


def bundle_with_claim(evidence_ids=("index.spx.change_percent",), source_time=AS_OF):
    return ResearchBundle(
        as_of=AS_OF,
        claims=(
            ResearchClaim(
                claim="SPX rose 0.16%",
                evidence_ids=tuple(evidence_ids),
                sources=("https://example.test/source",),
                confidence="confirmed",
            ),
        ),
        source_times=(source_time,),
        provider="fixture",
        model="fixture",
    )


def test_validator_rejects_claim_with_unknown_evidence():
    result = validate_research_bundle(bundle_with_claim(("missing.fact",)), [FACT], [], AS_OF)
    assert result.errors == ["unknown_evidence:missing.fact"]


def test_validator_rejects_source_after_cutoff():
    result = validate_research_bundle(
        bundle_with_claim(source_time=AS_OF + timedelta(minutes=1)), [FACT], [], AS_OF
    )
    assert "source_after_cutoff" in result.errors


def test_conflicting_model_number_does_not_replace_fact():
    result = apply_research_bundle([FACT], bundle_with_claim())
    assert result.facts == [FACT]
    assert result.warnings == []
