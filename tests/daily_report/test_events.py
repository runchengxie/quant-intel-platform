from dataclasses import replace
from datetime import UTC, datetime, timedelta

from daily_messenger.daily_report.events import build_market_events, filter_events_as_of

AS_OF = datetime(2026, 9, 19, 1, tzinfo=UTC)


def test_event_preserves_actual_previous_forecast_and_revised_values():
    row = {
        "id": "industrial-production-2026-08",
        "event_type": "economic",
        "title": "Industrial Production",
        "actual": "0.0%",
        "forecast": "+0.3%",
        "previous": "+0.2%",
        "revised": None,
        "source": "trading_economics",
        "source_url": "https://example.test/event",
        "source_time": AS_OF,
    }
    event = build_market_events([row], as_of=AS_OF)[0]
    assert event.actual == "0.0%"
    assert event.forecast == "+0.3%"
    assert event.previous == "+0.2%"


def test_future_event_is_excluded_from_report_cutoff():
    rows = [
        {
            "id": "past",
            "event_type": "news",
            "title": "Past",
            "source": "rss",
            "source_time": AS_OF,
        },
        {
            "id": "future",
            "event_type": "news",
            "title": "Future",
            "source": "rss",
            "source_time": AS_OF + timedelta(minutes=1),
        },
    ]
    events = build_market_events(rows, as_of=AS_OF)
    assert [event.id for event in filter_events_as_of(events, AS_OF)] == ["past"]


def test_date_only_event_filter_uses_end_of_possible_interval():
    event = build_market_events([{"id": "release", "source_time": AS_OF}], as_of=AS_OF)[0]
    event = replace(
        event,
        source_time=None,
        publication_precision="date",
        source_date="2026-09-18",
        source_timezone="unknown",
        time_role="publication",
        usage="background",
    )
    assert filter_events_as_of([event], AS_OF) == []
    assert filter_events_as_of([event], datetime(2026, 9, 19, 12, tzinfo=UTC)) == [event]
