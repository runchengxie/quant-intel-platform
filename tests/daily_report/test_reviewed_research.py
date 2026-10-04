import hashlib
import json
from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report.pipeline import run_daily_report
from daily_messenger.daily_report.reviewed_research import load_reviewed_research

AS_OF = datetime(2026, 9, 24, 8, 30, tzinfo=UTC)


def _news_files(tmp_path):
    draft, review = _files(tmp_path)
    payload = json.loads(draft.read_text())
    item = payload["candidates"][0]
    item.pop("published_at")
    item.update(
        section="company_news",
        phase="event",
        publication_precision="date",
        source_date="2026-09-23",
        source_timezone="unknown",
        time_role="publication",
        usage="background",
    )
    draft.write_text(json.dumps(payload))
    approvals = json.loads(review.read_text())
    approvals["draft_sha256"] = hashlib.sha256(draft.read_bytes()).hexdigest()
    row = approvals["decisions"][0]
    row.pop("index_returns")
    row.pop("index_evidence")
    row.update(
        source_locator="Issuer release, revenue paragraph",
        verified_facts=["Revenue grew"],
        display_basis={
            "basis": "independent_factual_summary",
            "scope": "short factual summary",
            "source_url": item["source_url"],
            "verified_on": "2026-09-24",
        },
    )
    review.write_text(json.dumps(approvals))
    return draft, review


def test_news_only_date_background_keeps_precision_and_hash_namespaced_identity(tmp_path):
    draft, review = _news_files(tmp_path)
    result = load_reviewed_research(
        draft,
        review,
        market_date="2026-09-23",
        as_of=datetime(2026, 9, 24, 13, tzinfo=UTC),
        news_only=True,
    )
    assert result.events[0].source_time is None
    assert result.events[0].source_date == "2026-09-23"
    assert result.events[0].id == f"reviewed.{hashlib.sha256(draft.read_bytes()).hexdigest()}.0"
    assert result.facts == ()


@pytest.mark.parametrize("dimension", ["facts", "timing", "attribution", "source_use"])
@pytest.mark.parametrize("news_only", [True, False])
def test_approved_news_cannot_override_a_blocked_review_dimension(tmp_path, dimension, news_only):
    draft, review = _news_files(tmp_path)
    payload = json.loads(review.read_text())
    checks = {
        key: {"status": "passed", "reason": "Independently reviewed"}
        for key in ("facts", "timing", "attribution", "source_use")
    }
    checks[dimension] = {"status": "blocked", "reason": "Evidence still missing"}
    payload["decisions"][0]["review_checks"] = checks
    review.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="review dimension"):
        load_reviewed_research(
            draft,
            review,
            market_date="2026-09-23",
            as_of=datetime(2026, 9, 24, 13, tzinfo=UTC),
            news_only=news_only,
        )


@pytest.mark.parametrize("news_only", [True, False])
@pytest.mark.parametrize("background", [True, False])
def test_layered_attribution_exemption_requires_background(tmp_path, news_only, background):
    draft, review = _news_files(tmp_path)
    candidate_payload = json.loads(draft.read_text())
    if not background:
        candidate_payload["candidates"][0].update(
            section="drivers",
            phase="close",
            usage="context",
            publication_precision="timestamp",
            published_at="2026-09-23T21:00:00+00:00",
        )
        draft.write_text(json.dumps(candidate_payload))
    payload = json.loads(review.read_text())
    payload["draft_sha256"] = hashlib.sha256(draft.read_bytes()).hexdigest()
    payload["decisions"][0]["review_checks"] = {
        key: {
            "status": "not_applicable" if key == "attribution" else "passed",
            "reason": "PRIVATE_REVIEW_SENTINEL",
        }
        for key in ("facts", "timing", "attribution", "source_use")
    }
    review.write_text(json.dumps(payload))
    kwargs = {
        "market_date": "2026-09-23",
        "as_of": datetime(2026, 9, 24, 13, tzinfo=UTC),
        "news_only": news_only,
    }
    if background:
        result = load_reviewed_research(draft, review, **kwargs)
        assert result.events
        assert "PRIVATE_REVIEW_SENTINEL" not in repr(result)
    else:
        with pytest.raises(ValueError, match="review dimension"):
            load_reviewed_research(draft, review, **kwargs)


@pytest.mark.parametrize(
    "checks",
    [
        None,
        {},
        {"facts": []},
        {
            key: {"status": [], "reason": "Checked"}
            for key in ("facts", "timing", "attribution", "source_use")
        },
        {
            key: {"status": "passed", "reason": " "}
            for key in ("facts", "timing", "attribution", "source_use")
        },
    ],
)
def test_layered_review_rejects_malformed_checks(tmp_path, checks):
    draft, review = _news_files(tmp_path)
    payload = json.loads(review.read_text())
    payload["decisions"][0]["review_checks"] = checks
    review.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="review dimension"):
        load_reviewed_research(
            draft,
            review,
            market_date="2026-09-23",
            as_of=datetime(2026, 9, 24, 13, tzinfo=UTC),
            news_only=True,
        )


def test_date_only_review_rejects_quotation_decisions_in_legacy_mode(tmp_path):
    draft, review = _news_files(tmp_path)
    payload = json.loads(review.read_text())
    payload["decisions"][0]["index_returns"] = {"spx": 1.0}
    review.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="date-only"):
        load_reviewed_research(
            draft, review, market_date="2026-09-23", as_of=datetime(2026, 9, 24, 13, tzinfo=UTC)
        )


@pytest.mark.parametrize("field", ["source_locator", "verified_facts", "display_basis"])
def test_new_mode_requires_private_source_and_display_review(tmp_path, field):
    draft, review = _news_files(tmp_path)
    payload = json.loads(review.read_text())
    payload["decisions"][0].pop(field)
    review.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="review"):
        load_reviewed_research(
            draft,
            review,
            market_date="2026-09-23",
            as_of=datetime(2026, 9, 24, 13, tzinfo=UTC),
            news_only=True,
        )


def test_private_source_locator_cannot_be_blank(tmp_path):
    draft, review = _news_files(tmp_path)
    payload = json.loads(review.read_text())
    payload["decisions"][0]["source_locator"] = "   "
    review.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="review"):
        load_reviewed_research(
            draft,
            review,
            market_date="2026-09-23",
            as_of=datetime(2026, 9, 24, 13, tzinfo=UTC),
            news_only=True,
        )


def test_precise_preclose_article_cannot_supply_reviewed_index_returns(tmp_path):
    draft, review = _files(tmp_path)
    payload = json.loads(draft.read_text())
    payload["candidates"][0]["published_at"] = "2026-09-23T15:59:00-04:00"
    draft.write_text(json.dumps(payload))
    approvals = json.loads(review.read_text())
    approvals["draft_sha256"] = hashlib.sha256(draft.read_bytes()).hexdigest()
    review.write_text(json.dumps(approvals))
    with pytest.raises(ValueError, match="close"):
        load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)


@pytest.mark.parametrize("field", ["ticker", "index_returns", "index_evidence"])
def test_news_only_rejects_quote_instructions_even_when_deferred(tmp_path, field):
    draft, review = _news_files(tmp_path)
    payload = json.loads(review.read_text())
    payload["decisions"][0].update(status="deferred")
    payload["decisions"][0][field] = None
    review.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="news-only"):
        load_reviewed_research(
            draft,
            review,
            market_date="2026-09-23",
            as_of=datetime(2026, 9, 24, 13, tzinfo=UTC),
            news_only=True,
        )


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


def test_only_explicitly_reviewed_mover_tickers_are_selected(tmp_path):
    draft, review = _files(tmp_path)
    artifact = json.loads(draft.read_text())
    artifact["candidates"][0]["section"] = "gainers"
    draft.write_text(json.dumps(artifact))
    decisions = json.loads(review.read_text())
    decisions["draft_sha256"] = hashlib.sha256(draft.read_bytes()).hexdigest()
    decisions["decisions"][0].pop("index_returns")
    decisions["decisions"][0].pop("index_evidence")
    decisions["decisions"][0]["ticker"] = "AKAM"
    review.write_text(json.dumps(decisions))
    result = load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)
    assert result.mover_tickers == ("AKAM",)
    assert result.mover_evidence == (("AKAM", "reviewed.0"),)
    decisions["decisions"][0]["ticker"] = "../../wrong"
    review.write_text(json.dumps(decisions))
    with pytest.raises(ValueError, match="ticker"):
        load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)


def test_abcnews_cdn_ap_close_source_is_eligible_for_reviewed_index_facts(tmp_path):
    draft, review = _files(tmp_path)
    artifact = json.loads(draft.read_text())
    artifact["candidates"][0]["source_url"] = (
        "https://www-cdn.abcnews.com/Business/wireStory/ap-recap"
    )
    draft.write_text(json.dumps(artifact))
    decisions = json.loads(review.read_text())
    decisions["draft_sha256"] = hashlib.sha256(draft.read_bytes()).hexdigest()
    review.write_text(json.dumps(decisions))

    result = load_reviewed_research(draft, review, market_date="2026-09-23", as_of=AS_OF)
    assert len(result.facts) == 4


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

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return AS_OF.astimezone(tz) if tz else AS_OF.replace(tzinfo=None)

    monkeypatch.setattr("daily_messenger.daily_report.pipeline.datetime", FixedDateTime)
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
