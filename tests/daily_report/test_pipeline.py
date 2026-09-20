from datetime import UTC, datetime

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
