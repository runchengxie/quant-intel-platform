from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report.models import DailyReport, MarketEvent, MarketFact


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


def test_date_only_event_round_trip_has_no_fabricated_time():
    payload = {
        "id": "news",
        "event_type": "web_company_news_event",
        "title": "Release",
        "actual": "Revenue grew",
        "previous": None,
        "forecast": None,
        "revised": None,
        "source": "issuer.test",
        "source_url": "https://issuer.test/release",
        "source_time": None,
        "quality": "reviewed",
        "publication_precision": "date",
        "source_date": "2026-10-02",
        "source_timezone": "unknown",
        "time_role": "publication",
        "usage": "background",
    }
    assert MarketEvent.from_dict(payload).to_dict() == payload


def test_legacy_event_projection_does_not_gain_optional_fields():
    payload = {
        "id": "news",
        "event_type": "web_macro_event",
        "title": "Release",
        "actual": "Payrolls",
        "previous": None,
        "forecast": None,
        "revised": None,
        "source": "agency.test",
        "source_url": "https://agency.test/release",
        "source_time": datetime(2026, 10, 2, 12, tzinfo=UTC),
        "quality": "reviewed",
    }
    assert MarketEvent.from_dict(payload).to_dict() == payload
