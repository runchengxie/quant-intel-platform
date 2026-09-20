from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report.models import DailyReport, MarketFact


def test_fact_round_trip_preserves_provenance():
    fact = MarketFact(
        id="spx.close",
        metric="index_return",
        instrument="SPX",
        value=0.16,
        previous=0.0,
        change=0.16,
        unit="percent",
        source="fmp",
        source_url="https://example.test/spx",
        source_time=datetime(2026, 9, 18, 20, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 19, 1, tzinfo=UTC),
        quality="ok",
    )
    assert MarketFact.from_dict(fact.to_dict()) == fact


def test_report_requires_schema_version_and_as_of():
    with pytest.raises(ValueError, match="schema_version"):
        DailyReport.from_dict({"sections": []})
