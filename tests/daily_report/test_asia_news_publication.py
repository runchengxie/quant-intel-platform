"""Only exact reviewed evidence can cross the public artifact boundary."""

import json
from dataclasses import asdict
from hashlib import sha256

import pytest

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
