"""Source-time regressions: retrieval time must never manufacture publication time."""

from datetime import date, datetime

import pytest

from daily_messenger.daily_report.asia_news_contract import (
    candidate_applicability,
    validate_asia_candidate,
)


def candidate_payload(**changes):
    return {
        "schema_version": "market_intel.asia_news_candidate.v1",
        "collector_identity": "collector-a",
        "market": "cn",
        "source_url": "https://www.sse.com.cn/disclosure/example.html",
        "publisher": "SSE",
        "published_at": "2026-09-30T14:00:00+08:00",
        "time_precision": "timestamp",
        "retrieved_at": "2026-09-30T18:00:00+08:00",
        "language": "zh-CN",
        "title": "公司公告",
        "summary": "收入增长 6%。",
        "source_sha256": "a" * 64,
        "document_status": "active",
        **changes,
    }


def applicability(candidate, **changes):
    return candidate_applicability(
        candidate,
        **{
            "cutoff": datetime.fromisoformat("2026-09-30T19:00:00+08:00"),
            "open_dates": [date(2026, 9, 29), date(2026, 9, 30)],
            "calendar_from": date(2026, 9, 29),
            "calendar_through": date(2026, 10, 2),
            **changes,
        },
    )


def test_preserves_source_value_and_utc_retrieval():
    item = validate_asia_candidate(candidate_payload())
    assert item.published_at == "2026-09-30T14:00:00+08:00"
    assert item.retrieved_at == "2026-09-30T10:00:00+00:00"
    assert applicability(item) == "eligible"


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"published_at": "2026-09-30", "time_precision": "date"}, "time_unverified"),
        ({"published_at": "2026-09-29", "time_precision": "date"}, "eligible"),
        (
            {
                "published_at": "2026-09-30T19:01:00+08:00",
                "retrieved_at": "2026-09-30T20:00:00+08:00",
            },
            "after_cutoff",
        ),
        (
            {
                "published_at": "2026-10-01",
                "time_precision": "date",
                "retrieved_at": "2026-10-02T10:00:00+08:00",
            },
            "after_cutoff",
        ),
        (
            {
                "published_at": "2026-09-29T23:30:00-04:00",
                "retrieved_at": "2026-09-30T18:00:00+08:00",
            },
            "eligible",
        ),
    ],
)
def test_applicability_uses_original_precision_and_market_timezone(changes, status):
    assert applicability(validate_asia_candidate(candidate_payload(**changes))) == status


@pytest.mark.parametrize(
    "changes",
    [
        {"published_at": ""},
        {"published_at": "2026-09-30T14:00:00"},
        {"published_at": "2026-02-30", "time_precision": "date"},
        {"source_sha256": "bad"},
        {"source_url": "http://www.sse.com.cn/x"},
        {"source_url": "https://user:password@www.sse.com.cn/x"},
        {"source_url": "https://127.0.0.1/x"},
        {"market": "jp"},
        {"collector_identity": ""},
        {"schema_version": "legacy"},
        {"retrieved_at": "2026-09-30T13:00:00+08:00"},
    ],
)
def test_invalid_candidate_is_rejected(changes):
    with pytest.raises(ValueError):
        validate_asia_candidate(candidate_payload(**changes))


def test_market_specific_calendar_and_unknown_coverage():
    item = validate_asia_candidate(candidate_payload(market="hk"))
    assert applicability(item, open_dates=[date(2026, 9, 29)]) == "holiday_context"
    assert applicability(item, calendar_through=date(2026, 9, 29)) == "calendar_unverified"
    assert applicability(item, calendar_from=date(2026, 10, 1)) == "calendar_unverified"


def test_content_changes_invalidate_identity_and_cancelled_items_cannot_publish():
    first = validate_asia_candidate(candidate_payload())
    changed = validate_asia_candidate(candidate_payload(summary="收入增长 7%。"))
    assert first.evidence_id != changed.evidence_id
    cancelled = validate_asia_candidate(candidate_payload(document_status="cancelled"))
    assert applicability(cancelled) == "cancelled"
