from datetime import UTC, datetime

from daily_messenger.daily_report.models import DailyReport, MarketEvent, MarketFact
from daily_messenger.daily_report.serialization import dumps_json


def test_dumps_json_uses_utc_iso_timestamps():
    fact = MarketFact(
        id="spx.close",
        metric="index_return",
        instrument="SPX",
        value=1.0,
        previous=0.0,
        change=1.0,
        unit="percent",
        source="fmp",
        source_url="https://example.test",
        source_time=datetime(2026, 9, 18, 20, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 19, 1, tzinfo=UTC),
        quality="ok",
    )
    assert "2026-09-18T20:00:00+00:00" in dumps_json(fact)


def test_legacy_event_json_artifact_does_not_gain_precision_fields():
    import json

    instant = datetime(2026, 10, 2, 23, tzinfo=UTC)
    event = MarketEvent(
        "release",
        "news",
        "Title",
        "Fact",
        None,
        None,
        None,
        "source",
        "https://issuer.test",
        instant,
        "reviewed",
    )
    report = DailyReport("1.0", instant, instant, "daily-2026-10-02", events=(event,))
    serialized = json.loads(dumps_json(report))
    assert "publication_precision" not in serialized["events"][0]
    assert serialized["events"][0] == json.loads(dumps_json(event.to_dict()))
