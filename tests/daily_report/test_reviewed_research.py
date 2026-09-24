import hashlib
import json
from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report.pipeline import run_daily_report
from daily_messenger.daily_report.reviewed_research import load_reviewed_research

AS_OF = datetime(2026, 9, 24, 8, 30, tzinfo=UTC)


def _files(tmp_path, *, decision="approved", summary="经核实的收盘摘要"):
    artifact = {
        "market_date": "2026-09-23",
        "candidates": [
            {
                "section": "market",
                "title": "AP recap",
                "source_url": "https://abcnews.com/amp/Business/ap-recap",
                "published_at": "2026-09-23T16:12:00-04:00",
                "observation_date": "2026-09-23",
                "phase": "close",
                "summary": "model draft",
                "review_status": "needs_review",
            }
        ],
    }
    artifact_path = tmp_path / "draft.json"
    artifact_path.write_text(json.dumps(artifact))
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps(
            {
                "market_date": "2026-09-23",
                "draft_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                "reviewer": "source-audit",
                "decisions": [
                    {
                        "index": 0,
                        "status": decision,
                        "reason": "Original page checked",
                        "approved_summary": summary,
                        "index_returns": {
                            "spx": -0.8,
                            "dow": -0.7,
                            "nasdaq": -1.1,
                            "russell2000": -1.8,
                        },
                        "index_evidence": {
                            "spx": {"reported_change": -0.8, "locator": "AP close: S&P"},
                            "dow": {"reported_change": -0.7, "locator": "AP close: Dow"},
                            "nasdaq": {"reported_change": -1.1, "locator": "AP close: Nasdaq"},
                            "russell2000": {
                                "reported_change": -1.8,
                                "locator": "AP close: Russell",
                            },
                        },
                    }
                ],
            }
        )
    )
    return artifact_path, review_path


def test_only_explicitly_approved_hash_bound_claims_enter_report(tmp_path):
    draft, review = _files(tmp_path)
    result = load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)
    assert len(result.claims) == 1
    assert result.claims[0].claim == "经核实的收盘摘要"
    assert result.claims[0].evidence_ids == ("reviewed.0",)
    assert len(result.facts) == 4
    assert result.facts[0].observation_date == "2026-09-23"
    assert result.facts[0].source_url == "https://abcnews.com/amp/Business/ap-recap"


def test_deferred_candidates_do_not_enter_report(tmp_path):
    draft, review = _files(tmp_path, decision="deferred")
    result = load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)
    assert result.claims == ()
    assert result.facts == ()


def test_index_fact_needs_approved_source_and_itemized_numeric_evidence(tmp_path):
    draft, review = _files(tmp_path)
    decisions = json.loads(review.read_text())
    decisions["decisions"][0]["index_evidence"]["spx"]["reported_change"] = 0.8
    review.write_text(json.dumps(decisions))
    with pytest.raises(ValueError, match="disagrees"):
        load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)

    draft, review = _files(tmp_path)
    artifact = json.loads(draft.read_text())
    artifact["candidates"][0]["source_url"] = "https://example.com/recap"
    draft.write_text(json.dumps(artifact))
    decisions = json.loads(review.read_text())
    decisions["draft_sha256"] = hashlib.sha256(draft.read_bytes()).hexdigest()
    review.write_text(json.dumps(decisions))
    with pytest.raises(ValueError, match="AP source"):
        load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)


def test_changed_draft_or_future_source_fails_closed(tmp_path):
    draft, review = _files(tmp_path)
    draft.write_text(draft.read_text() + " ")
    with pytest.raises(ValueError, match="hash"):
        load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)
    draft, review = _files(tmp_path)
    with pytest.raises(ValueError, match="cutoff"):
        load_reviewed_research(
            draft, review, market_date="2026-09-23", as_of=datetime(2026, 9, 23, 19, tzinfo=UTC)
        )


def test_live_pipeline_includes_only_reviewed_facts_and_claims(monkeypatch, tmp_path):
    draft, review = _files(tmp_path)
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_us_macro_facts",
        lambda _as_of: ([], {"rates": {"quality": "degraded"}, "macro": {"quality": "degraded"}}),
    )
    report = run_daily_report(
        datetime(2026, 9, 23, 23, 0, tzinfo=UTC),
        tmp_path / "out",
        provider_config={
            "mode": "live",
            "reviewed_draft": str(draft),
            "reviewed_decisions": str(review),
        },
    )
    assert len(report.claims) == 1
    assert len(report.events) == 1
    assert len([fact for fact in report.facts if fact.id.startswith("index.")]) == 4
    assert "quotes" not in report.missing_sources
    assert "research" not in report.missing_sources
    assert report.quality_summary["revision"] == "next_morning_rechecked"
    assert report.quality_summary["reviewed_source_cutoff"] == "2026-09-23T23:00:00+00:00"
