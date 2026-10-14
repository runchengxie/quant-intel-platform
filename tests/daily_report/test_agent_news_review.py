import json

import pytest

from market_intel_publication.agent_research_review import ReportInput, read_research_review
from tests.daily_report.test_news_revision import inputs, revision


def test_news_revision_comparison_retains_parent_and_precision(tmp_path):
    paths = inputs(tmp_path)
    revised = revision(paths, tmp_path / "stage").artifact_path
    manifest = revised.parent / "publication.json"
    with pytest.raises(ValueError, match="immutable original"):
        read_research_review(
            ReportInput(paths[0], paths[1], "2026-10-02"),
            ReportInput(revised, manifest, "2026-10-02"),
        )
    result = read_research_review(
        ReportInput(paths[0], paths[1], "2026-10-02"),
        ReportInput(revised, manifest, "2026-10-02", paths[0]),
    )
    assert result["comparison_kind"] == "revision"
    assert result["fact_changes"][0]["delta"] == 0
    assert result["claim_changes"][0]["status"] == "added"
    identifier = result["claim_changes"][0]["evidence_ids"][0]
    evidence = result["evidence"]["current"][identifier]
    assert evidence["source_time"] is None
    assert evidence["publication_precision"] == "date"
    assert result["validation"]["watchpoint_outcomes"] == "not_provided"
    assert result["current"]["generated_at"] == "2026-10-04T01:00:00+00:00"
    assert json.loads(paths[0].read_text())["generated_at"] == "2026-10-02T23:00:00+00:00"
