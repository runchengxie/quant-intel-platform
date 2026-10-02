"""Changed content, producer self-approval and absent rights notes cannot publish."""

from datetime import datetime

import pytest

from daily_messenger.daily_report.asia_news_contract import digest, validate_asia_candidate
from daily_messenger.daily_report.asia_news_review import review_template, validate_asia_review
from tests.daily_report.test_asia_news_contract import candidate_payload

CUTOFF = datetime.fromisoformat("2026-09-30T19:00:00+08:00")


def reviewed_fixture(**candidate_changes):
    candidate = validate_asia_candidate(candidate_payload(**candidate_changes))
    review = {
        "schema_version": "market_intel.asia_news_review.v1",
        "status": "approved",
        "reviewer": "independent-reviewer",
        "reviewed_at": "2026-09-30T20:00:00+08:00",
        "cutoff": CUTOFF.isoformat(),
        "candidate_sha256": candidate.evidence_id.removeprefix("asia."),
        "source_sha256": candidate.source_sha256,
        "source_url": candidate.source_url,
        "claim": "收入增长 6%。",
        "claim_sha256": digest("收入增长 6%。"),
        "source_date_note": "Original publication timestamp checked.",
        "fact_note": "6% checked against original disclosure.",
        "rights_note": "Short original factual paraphrase with source link.",
        "applicability_note": "Same-session source at report cutoff.",
        "calendar": {
            "market": candidate.market,
            "from": "2026-09-29",
            "through": "2026-10-02",
            "open_dates": ["2026-09-29", "2026-09-30"],
            "source_url": "https://www.sse.com.cn/calendar",
            "source_sha256": "b" * 64,
        },
        "translation": {
            "text": "Revenue rose 6%.",
            "sha256": digest("Revenue rose 6%."),
            "claim_sha256": digest("收入增长 6%。"),
            "reviewer": "translation-reviewer",
            "reviewed_at": "2026-09-30T20:00:00+08:00",
            "note": "Numbers, units, entity and meaning verified.",
        },
    }
    return candidate, review


def test_independent_exact_review_passes_and_binds_translation():
    candidate, review = reviewed_fixture()
    result = validate_asia_review(candidate, review, cutoff=CUTOFF)
    assert result["claim"] == "收入增长 6%。"
    assert result["translation"]["text"] == "Revenue rose 6%."
    assert result["applicability"] == "eligible"


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "needs_review"},
        {"reviewer": "collector-a"},
        {"reviewer": ""},
        {"candidate_sha256": "c" * 64},
        {"source_sha256": "c" * 64},
        {"source_url": "https://www.sse.com.cn/other"},
        {"claim": "收入增长 7%。"},
        {"rights_note": ""},
        {"fact_note": ""},
        {"source_date_note": ""},
        {"reviewed_at": "2026-09-30T20:00:00"},
        {"cutoff": "2026-10-01T19:00:00+08:00"},
    ],
)
def test_invalid_receipts_rejected(changes):
    candidate, review = reviewed_fixture()
    with pytest.raises(ValueError):
        validate_asia_review(candidate, {**review, **changes}, cutoff=CUTOFF)


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "Revenue rose 7%."},
        {"claim_sha256": "c" * 64},
        {"reviewer": "collector-a"},
        {"note": ""},
        {"text": "Revenue rose 7%.", "sha256": digest("Revenue rose 7%.")},
    ],
)
def test_translation_tampering_and_changed_numbers_rejected(changes):
    candidate, review = reviewed_fixture()
    review["translation"].update(changes)
    with pytest.raises(ValueError):
        validate_asia_review(candidate, review, cutoff=CUTOFF)


def test_calendar_market_missing_or_out_of_coverage_blocks_claim():
    candidate, review = reviewed_fixture()
    for change in [{"market": "hk"}, {"through": "2026-09-29"}, {"source_sha256": "bad"}]:
        with pytest.raises(ValueError):
            validate_asia_review(
                candidate, {**review, "calendar": {**review["calendar"], **change}}, cutoff=CUTOFF
            )


@pytest.mark.parametrize(
    "changes",
    [
        {"document_status": "cancelled"},
        {"published_at": "2026-09-30", "time_precision": "date"},
        {"published_at": "2026-09-30T19:01:00+08:00", "retrieved_at": "2026-09-30T20:00:00+08:00"},
    ],
)
def test_cutoff_uncertainty_and_withdrawal_block_even_with_approved_receipt(changes):
    candidate, review = reviewed_fixture(**changes)
    with pytest.raises(ValueError):
        validate_asia_review(candidate, review, cutoff=CUTOFF)


def test_template_cannot_approve_and_revision_requires_new_receipt():
    candidate, review = reviewed_fixture()
    template = review_template(candidate, cutoff=CUTOFF)
    assert template["status"] == "needs_review"
    with pytest.raises(ValueError):
        validate_asia_review(candidate, template, cutoff=CUTOFF)
    revised = validate_asia_candidate(
        candidate_payload(
            document_status="revised", revision_of=candidate.evidence_id, source_sha256="c" * 64
        )
    )
    with pytest.raises(ValueError):
        validate_asia_review(revised, review, cutoff=CUTOFF)


def test_missing_translation_is_explicit_and_holiday_context_retained():
    candidate, review = reviewed_fixture()
    review.pop("translation")
    review["calendar"]["open_dates"] = ["2026-09-29"]
    result = validate_asia_review(candidate, review, cutoff=CUTOFF)
    assert result["translation"] is None
    assert result["applicability"] == "holiday_context"
