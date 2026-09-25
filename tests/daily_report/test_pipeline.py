from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report.pipeline import run_daily_report

AS_OF = datetime(2026, 9, 19, 1, tzinfo=UTC)


def test_pipeline_keeps_facts_when_research_provider_fails(tmp_path):
    report = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "fail"})
    assert report.source_status["research"]["quality"] == "degraded"
    assert report.facts


def test_second_run_reuses_same_artifact_hash(tmp_path):
    first = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "fixture"})
    second = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "fixture"})
    assert first.run_id == second.run_id
    assert first.content_hash == second.content_hash


@pytest.mark.parametrize(
    ("missing", "expected_quality"),
    [((), "ok"), (("GC=F",), "degraded")],
)
def test_pipeline_records_cross_asset_coverage(monkeypatch, tmp_path, missing, expected_quality):
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_us_macro_facts",
        lambda _as_of: ([], {"macro": {"quality": "ok"}, "rates": {"quality": "ok"}}),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_cross_asset_facts",
        lambda _date: ([], missing),
    )

    report = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "live"})
    section = next(section for section in report.sections if section.key == "cross_asset")

    assert section.facts == ()
    assert report.source_status["cross_asset"]["quality"] == expected_quality
    assert ("cross_asset" in report.missing_sources) is bool(missing)
    assert report.quality_summary["status"] == "degraded"
