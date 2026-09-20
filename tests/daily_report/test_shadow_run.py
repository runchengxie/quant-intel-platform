from daily_messenger.daily_report.pipeline import shadow_run


def test_shadow_run_records_source_coverage_and_degraded_sections(tmp_path):
    result = shadow_run("2026-09-18", tmp_path, provider_config={"mode": "fail"})
    assert result.artifact_path.endswith("daily_report.json")
    assert result.source_coverage >= 0
    assert result.degraded_sections == ["research"]
