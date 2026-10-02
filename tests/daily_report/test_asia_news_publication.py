"""Only exact reviewed evidence can cross the public artifact boundary."""

import json
from dataclasses import asdict
from hashlib import sha256

import pytest

from daily_messenger.daily_report.asia_news_contract import digest, validate_asia_candidate
from market_intel_publication.asia_news_contract import (
    build_public_asia_news,
    validate_public_asia_news,
)
from tests.daily_report.test_asia_news_review import reviewed_fixture

REPORT = "# 收盘复盘\n生成时间: 2026-09-30 20:00\n## 盘面\n上涨 2567 家。\n"
REPORT_HASH = sha256(REPORT.encode()).hexdigest()


def build(rows):
    return build_public_asia_news(
        rows,
        report_date="2026-09-30",
        generated_at="2026-09-30T20:30:00+08:00",
        report_sha256=REPORT_HASH,
    )


def fixture_row(market="cn"):
    candidate, review = reviewed_fixture(market=market)
    return {"candidate": asdict(candidate), "review": review}


def test_separate_markets_and_public_projection_excludes_private_receipts():
    result = build([fixture_row(), fixture_row("hk")])
    assert [item["market"] for item in result["markets"]["cn"]] == ["cn"]
    assert result["markets"]["hk"][0]["claim_en"] == "Revenue rose 6%."
    assert result["report_sha256"] == REPORT_HASH
    assert result["status"] == "reviewed"
    assert "collector-a" not in json.dumps(result)
    assert "rights_note" not in json.dumps(result)
    validate_public_asia_news(result, report_id="2026-09-30-evening", report_sha256=REPORT_HASH)


def test_missing_translation_and_empty_collection_are_explicit():
    row = fixture_row()
    row["review"].pop("translation")
    assert build([row])["markets"]["cn"][0]["claim_en"] is None
    assert build([])["status"] == "missing"
    assert build([])["markets"] == {"cn": [], "hk": []}


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_sha256": "c" * 64},
        {"status": "needs_review"},
        {"claim": "/home/richard/private"},
    ],
)
def test_invalid_review_cannot_publish(changes):
    row = fixture_row()
    row["review"].update(changes)
    with pytest.raises(ValueError):
        build([row])


def test_public_validation_rejects_stale_report_and_tampered_artifact():
    payload = build([fixture_row()])
    with pytest.raises(ValueError):
        validate_public_asia_news(payload, report_id="2026-09-30-evening", report_sha256="c" * 64)
    payload["markets"]["cn"][0]["claim"] = "收入增长 7%。"
    with pytest.raises(ValueError):
        validate_public_asia_news(
            payload, report_id="2026-09-30-evening", report_sha256=REPORT_HASH
        )


def test_after_cutoff_source_blocked_and_future_generation_cutoff_not_invented():
    candidate, review = reviewed_fixture(
        published_at="2026-09-30T19:01:00+08:00", retrieved_at="2026-09-30T20:00:00+08:00"
    )
    with pytest.raises(ValueError):
        build([{"candidate": asdict(candidate), "review": review}])
    with pytest.raises(ValueError):
        build_public_asia_news(
            [],
            report_date="2026-09-30",
            generated_at="2026-09-30T18:45:00+08:00",
            report_sha256=REPORT_HASH,
        )


@pytest.mark.parametrize("field", ["private_receipt", "raw_body", "event_date"])
def test_public_unknown_fields_and_invalid_event_date_rejected(field):
    payload = build([fixture_row()])
    payload["markets"]["cn"][0][field] = "/home/private/raw"
    payload["content_sha256"] = digest({k: v for k, v in payload.items() if k != "content_sha256"})
    with pytest.raises(ValueError):
        validate_public_asia_news(
            payload, report_id="2026-09-30-evening", report_sha256=REPORT_HASH
        )


def test_private_envelope_rejected_even_with_valid_hash():
    payload = build([])
    payload["private_receipt"] = {"reviewer": "private"}
    payload["content_sha256"] = digest({k: v for k, v in payload.items() if k != "content_sha256"})
    with pytest.raises(ValueError):
        validate_public_asia_news(
            payload, report_id="2026-09-30-evening", report_sha256=REPORT_HASH
        )


@pytest.mark.parametrize("stamp", ["2026-10-02T20:00:00+08:00", "2026-09-30T17:00:00+08:00"])
def test_translation_review_must_fit_retrieval_and_generation(stamp):
    row = fixture_row()
    row["review"]["translation"]["reviewed_at"] = stamp
    with pytest.raises(ValueError, match="translation"):
        build([row])


def test_refetched_same_document_deduplicated_and_explicit_revision_supersedes():
    original = fixture_row()
    duplicate = fixture_row()
    duplicate["candidate"]["retrieved_at"] = "2026-09-30T18:01:00+08:00"
    duplicate["review"]["candidate_sha256"] = validate_asia_candidate(
        duplicate["candidate"]
    ).evidence_id[5:]
    assert len(build([original, duplicate])["markets"]["cn"]) == 1
    revision = fixture_row()
    revision["candidate"].update(
        document_status="revised",
        revision_of=validate_asia_candidate(original["candidate"]).evidence_id,
        source_sha256="c" * 64,
    )
    revision["review"].update(
        candidate_sha256=validate_asia_candidate(revision["candidate"]).evidence_id[5:],
        source_sha256="c" * 64,
        claim="收入增长 7%。",
        claim_sha256=digest("收入增长 7%。"),
    )
    revision["review"].pop("translation")
    assert [item["claim"] for item in build([original, revision])["markets"]["cn"]] == [
        "收入增长 7%。"
    ]
