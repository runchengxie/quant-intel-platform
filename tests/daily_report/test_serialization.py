from datetime import UTC, datetime

from daily_messenger.daily_report.models import MarketFact
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
