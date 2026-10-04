from datetime import UTC, datetime
from importlib import import_module

import pytest


def contract():
    return import_module("daily_messenger.daily_report.publication_time")


def test_unknown_timezone_bounds_are_conservative():
    api = contract()
    evidence = api.PublicationTime(
        "date", None, "2026-10-02", "unknown", "publication", "background"
    )
    start, end = api.publication_interval(evidence)
    assert start.isoformat() == "2026-10-01T10:00:00+00:00"
    assert end.isoformat() == "2026-10-03T12:00:00+00:00"
    with pytest.raises(ValueError, match="cutoff"):
        api.validate_publication_time(
            evidence,
            market_date="2026-10-02",
            cutoff=datetime(2026, 10, 3, 8, tzinfo=UTC),
            section="company_news",
        )
    api.validate_publication_time(
        evidence, market_date="2026-10-02", cutoff=end, section="company_news"
    )


def test_dst_day_uses_local_midnight_boundaries():
    api = contract()
    evidence = api.PublicationTime(
        "date", None, "2026-11-01", "America/New_York", "publication", "background"
    )
    start, end = api.publication_interval(evidence)
    assert start.isoformat() == "2026-11-01T04:00:00+00:00"
    assert end.isoformat() == "2026-11-02T05:00:00+00:00"
    assert (end - start).total_seconds() == 25 * 3600


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_timezone": "Invalid/Zone"},
        {"source_date": "20261002"},
        {"source_date": "2026-02-30"},
        {"source_date": "2026-10-05"},
        {"published_at": "2026-10-02T12:00:00Z"},
        {"usage": "close"},
        {"time_role": "unknown"},
    ],
)
def test_invalid_date_evidence_is_rejected(overrides):
    api = contract()
    candidate = {
        "publication_precision": "date",
        "source_date": "2026-10-02",
        "source_timezone": "unknown",
        "time_role": "publication",
        "usage": "background",
    } | overrides
    with pytest.raises(ValueError):
        evidence = api.publication_time_from_candidate(candidate)
        api.validate_publication_time(
            evidence,
            market_date="2026-10-02",
            cutoff=datetime(2026, 10, 4, tzinfo=UTC),
            section="macro",
        )


@pytest.mark.parametrize("section", ["market", "drivers", "gainers", "losers"])
def test_date_only_cannot_supply_close_or_mover_evidence(section):
    api = contract()
    evidence = api.PublicationTime(
        "date", None, "2026-10-02", "unknown", "publication", "background"
    )
    with pytest.raises(ValueError):
        api.validate_publication_time(
            evidence,
            market_date="2026-10-02",
            cutoff=datetime(2026, 10, 4, tzinfo=UTC),
            section=section,
        )


def test_precise_time_requires_zone_and_preserves_filing_role():
    api = contract()
    with pytest.raises(ValueError):
        api.publication_time_from_candidate({"published_at": "2026-10-02T12:00:00"})
    evidence = api.publication_time_from_candidate(
        {
            "published_at": "2026-10-02T12:00:00Z",
            "time_role": "filing_acceptance",
            "usage": "background",
        }
    )
    assert evidence.time_role == "filing_acceptance"
    assert evidence.source_time.isoformat() == "2026-10-02T12:00:00+00:00"
    with pytest.raises(ValueError):
        api.validate_publication_time(
            evidence,
            market_date="2026-10-02",
            cutoff=datetime(2026, 10, 4, tzinfo=UTC),
            section="drivers",
        )
