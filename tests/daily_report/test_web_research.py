from datetime import UTC, date, datetime

from daily_messenger.daily_report.web_research import validate_candidates

MARKET_DATE = date(2026, 9, 18)
CUTOFF = datetime(2026, 9, 19, 1, tzinfo=UTC)


def candidate(**overrides):
    row = {
        "section": "market",
        "title": "US stock indexes finish mixed",
        "source_url": "https://example.org/market-close",
        "published_at": "2026-09-18T21:30:00+00:00",
        "observation_date": "2026-09-18",
        "summary": "The S&P 500 rose while the Dow fell.",
        "supporting_passage": "The S&P 500 rose 0.2% Friday. The Dow slipped 0.2%.",
        "phase": "close",
    }
    row.update(overrides)
    return row


def test_valid_candidate_is_kept_for_review():
    accepted, rejected = validate_candidates(
        {"candidates": [candidate()]}, market_date=MARKET_DATE, cutoff=CUTOFF
    )
    assert rejected == []
    assert accepted[0]["review_status"] == "needs_review"
    assert accepted[0]["observation_date"] == "2026-09-18"


def test_previous_day_article_is_not_target_day_evidence():
    accepted, rejected = validate_candidates(
        {"candidates": [candidate(observation_date="2026-09-17")]},
        market_date=MARKET_DATE,
        cutoff=CUTOFF,
    )
    assert accepted == []
    assert rejected == ["candidate[0]:observation_date_mismatch"]


def test_future_source_and_timezone_less_source_are_rejected():
    accepted, rejected = validate_candidates(
        {
            "candidates": [
                candidate(published_at="2026-09-19T01:01:00+00:00"),
                candidate(published_at="2026-09-18T21:30:00"),
            ]
        },
        market_date=MARKET_DATE,
        cutoff=CUTOFF,
    )
    assert accepted == []
    assert rejected == ["candidate[0]:source_after_cutoff", "candidate[1]:invalid_published_at"]


def test_non_web_url_and_missing_passage_are_rejected():
    accepted, rejected = validate_candidates(
        {
            "candidates": [
                candidate(source_url="file:///tmp/article"),
                candidate(supporting_passage=""),
            ]
        },
        market_date=MARKET_DATE,
        cutoff=CUTOFF,
    )
    assert accepted == []
    assert rejected == ["candidate[0]:invalid_source_url", "candidate[1]:missing_support"]


def test_preclose_article_cannot_be_close_evidence():
    accepted, rejected = validate_candidates(
        {"candidates": [candidate(published_at="2026-09-18T19:59:00+00:00")]},
        market_date=MARKET_DATE,
        cutoff=CUTOFF,
    )
    assert accepted == []
    assert rejected == ["candidate[0]:preclose_source"]


def test_long_supporting_passage_is_rejected():
    accepted, rejected = validate_candidates(
        {"candidates": [candidate(supporting_passage="x" * 161)]},
        market_date=MARKET_DATE,
        cutoff=CUTOFF,
    )
    assert accepted == []
    assert rejected == ["candidate[0]:support_too_long"]


def test_malformed_container_is_rejected():
    accepted, rejected = validate_candidates([], market_date=MARKET_DATE, cutoff=CUTOFF)
    assert accepted == []
    assert rejected == ["invalid_payload"]
