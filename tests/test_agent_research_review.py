import hashlib
import json

import pytest

from daily_messenger.daily_report.serialization import content_digest
from tests.test_agent_market_brief import bundle


def report(tmp_path, name, day, value=1.0, *, claim=None):
    root = tmp_path / name
    root.mkdir()
    source, manifest = bundle(root)
    raw = json.loads(source.read_text())
    raw.update(
        run_id=f"daily-{day}", as_of=f"{day}T23:00:00+00:00", generated_at=f"{day}T23:30:00+00:00"
    )
    raw["facts"] = [
        {
            "id": "index.spx.change_percent",
            "metric": "daily_return",
            "instrument": "S&P 500",
            "value": value,
            "unit": "percent",
            "source": "synthetic reviewed source",
            "source_url": "https://example.test/close",
            "source_time": f"{day}T20:12:00+00:00",
            "retrieved_at": f"{day}T23:00:00+00:00",
            "observation_date": day,
            "quality": "reviewed",
        }
    ]
    raw["claims"] = (
        []
        if claim is None
        else [
            {
                "claim": claim,
                "evidence_ids": ["index.spx.change_percent"],
                "sources": ["https://example.test/close"],
                "status": "accepted",
                "confidence": "confirmed",
            }
        ]
    )
    raw["missing_sources"] = []
    seal(source, manifest, raw)
    return source, manifest


def seal(source, manifest, raw):
    raw["content_hash"] = content_digest(raw)
    source.write_text(json.dumps(raw))
    meta = json.loads(manifest.read_text())
    meta.update(
        run_id=raw["run_id"],
        content_hash=raw["content_hash"],
        report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    manifest.write_text(json.dumps(meta))


def compare(before, after, *, baseline_date="2026-10-02", current_date="2026-10-05"):
    from market_intel_publication.agent_research_review import ReportInput, read_research_review

    return read_research_review(
        ReportInput(*before, baseline_date), ReportInput(*after, current_date)
    )


def test_review_reports_measured_changes_and_preserves_evidence(tmp_path):
    baseline = report(tmp_path, "baseline", "2026-10-02", 1.0, claim="First interpretation")
    current = report(
        tmp_path,
        "current",
        "2026-10-05",
        3.0,
        claim="Revised interpretation",
    )
    for paths, missing in ((baseline, ["research"]), (current, ["cross_asset"])):
        raw = json.loads(paths[0].read_text())
        raw["missing_sources"] = missing
        seal(*paths, raw)
    original = [path.read_bytes() for path in (*baseline, *current)]
    result = compare(baseline, current)
    assert result["schema_version"] == "quant.research_review.v1"
    assert result["comparison_kind"] == "report_dates"
    row = result["fact_changes"][0]
    assert row["status"] == "changed"
    assert row["delta"] == 2.0
    assert row["delta_unit"] == "percentage_points"
    assert result["claim_changes"][0]["status"] == "revised"
    assert result["claim_changes"][0]["after"][0]["claim"] == "Revised interpretation"
    evidence = result["evidence"]["current"]["index.spx.change_percent"]
    assert evidence["source_time"] == "2026-10-05T20:12:00+00:00"
    assert evidence["source_url"] == "https://example.test/close"
    assert result["data_quality"]["missing_sources_added"] == ["cross_asset"]
    assert result["data_quality"]["missing_sources_resolved"] == ["research"]
    assert (
        result["baseline"]["artifact_hash"] == hashlib.sha256(baseline[0].read_bytes()).hexdigest()
    )
    assert result["validation"]["watchpoint_outcomes"] == "not_provided"
    assert result["validation"]["predictive_performance"] == "not_provided"
    assert "must not escape" not in json.dumps(result)
    assert original == [path.read_bytes() for path in (*baseline, *current)]


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("source", "another source"),
        ("source_url", "https://example.test/other"),
        ("instrument", "different index"),
        ("metric", "different metric"),
    ],
)
def test_changed_measurement_basis_has_no_numeric_delta(tmp_path, field, new_value):
    baseline = report(tmp_path, "baseline", "2026-10-02")
    current = report(tmp_path, "current", "2026-10-05", 3)
    raw = json.loads(current[0].read_text())
    raw["facts"][0][field] = new_value
    seal(*current, raw)
    result = compare(baseline, current)
    row = result["fact_changes"][0]
    assert row["status"] == "not_comparable"
    assert row["delta"] is None
    assert field in row["basis_changes"]


def test_missing_fact_is_missing_evidence_not_a_zero(tmp_path):
    baseline = report(tmp_path, "baseline", "2026-10-02", 3)
    current = report(tmp_path, "current", "2026-10-05")
    raw = json.loads(current[0].read_text())
    raw["facts"] = []
    seal(*current, raw)
    row = compare(baseline, current)["fact_changes"][0]
    assert row["status"] == "removed"
    assert row["after_value"] is None
    assert row["delta"] is None


def test_review_rejects_reverse_report_dates(tmp_path):
    baseline = report(tmp_path, "baseline", "2026-10-05")
    current = report(tmp_path, "current", "2026-10-02")
    with pytest.raises(ValueError, match="order"):
        compare(baseline, current, baseline_date="2026-10-05", current_date="2026-10-02")


def test_review_distinguishes_identical_snapshot_from_same_day_revision(tmp_path):
    baseline = report(tmp_path, "baseline", "2026-10-02", 1)
    result = compare(baseline, baseline, current_date="2026-10-02")
    assert result["comparison_kind"] == "identical_snapshot"
    assert result["fact_changes"][0]["status"] == "unchanged"
    current = report(tmp_path, "current", "2026-10-02", 2)
    raw = json.loads(current[0].read_text())
    raw["generated_at"] = "2026-10-03T00:00:00+00:00"
    seal(*current, raw)
    assert compare(baseline, current, current_date="2026-10-02")["comparison_kind"] == "revision"
    with pytest.raises(ValueError, match="order"):
        compare(current, baseline, current_date="2026-10-02")


def test_cli_fails_closed_when_either_report_is_tampered(tmp_path, capsys):
    from market_intel_publication.agent_research_review import main

    baseline = report(tmp_path, "baseline", "2026-10-02")
    current = report(tmp_path, "current", "2026-10-05")
    args = [
        "--baseline",
        str(baseline[0]),
        "--baseline-manifest",
        str(baseline[1]),
        "--baseline-date",
        "2026-10-02",
        "--current",
        str(current[0]),
        "--current-manifest",
        str(current[1]),
        "--current-date",
        "2026-10-05",
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["comparison_kind"] == "report_dates"
    baseline[0].write_text(baseline[0].read_text() + " ")
    assert main(args) == 2
    output = capsys.readouterr()
    assert not output.out
    assert output.err


def test_added_fact_and_claim_are_new_evidence_not_confirmed_prediction(tmp_path):
    baseline = report(tmp_path, "baseline", "2026-10-02")
    current = report(tmp_path, "current", "2026-10-05", claim="New descriptive statement")
    raw = json.loads(baseline[0].read_text())
    raw["facts"] = []
    seal(*baseline, raw)
    result = compare(baseline, current)
    assert result["fact_changes"][0]["status"] == "added"
    assert result["fact_changes"][0]["delta"] is None
    assert result["claim_changes"][0]["status"] == "added"
    assert result["validation"]["predictive_performance"] == "not_provided"


def test_review_rejects_ambiguous_same_time_different_revisions(tmp_path):
    baseline = report(tmp_path, "baseline", "2026-10-02", 1)
    current = report(tmp_path, "current", "2026-10-02", 3)
    with pytest.raises(ValueError, match="order"):
        compare(baseline, current, current_date="2026-10-02")


def test_unit_change_prevents_implicit_conversion():
    from market_intel_publication.agent_research_review import _fact_change

    before = {"value": 1, "unit": "USD"}
    after = {"value": 7, "unit": "CNY"}
    result = _fact_change("same_metric", before, after)
    assert result["status"] == "not_comparable"
    assert result["delta"] is None
    assert result["basis_changes"] == ["unit"]


def test_nonfinite_delta_is_rejected():
    from market_intel_publication.agent_research_review import _fact_change

    with pytest.raises(ValueError, match="finite"):
        _fact_change("same_metric", {"value": -1e308}, {"value": 1e308})


def test_review_rejects_colliding_fact_and_event_ids(tmp_path):
    baseline = report(tmp_path, "baseline", "2026-10-02", claim="Baseline")
    current = report(tmp_path, "current", "2026-10-05", claim="Current")
    raw = json.loads(current[0].read_text())
    raw["events"] = [{"id": "index.spx.change_percent"}]
    seal(*current, raw)
    with pytest.raises(ValueError, match="evidence"):
        compare(baseline, current)


def test_claim_reference_order_changes_do_not_revise_statement(tmp_path):
    baseline = report(tmp_path, "baseline", "2026-10-02", claim="Same statement")
    current = report(tmp_path, "current", "2026-10-05", claim="Same statement")
    for paths, sources in (
        (baseline, ["https://example.test/a", "https://example.test/b"]),
        (current, ["https://example.test/b", "https://example.test/a"]),
    ):
        raw = json.loads(paths[0].read_text())
        raw["claims"][0]["sources"] = sources
        seal(*paths, raw)
    assert compare(baseline, current)["claim_changes"][0]["status"] == "unchanged"


def test_review_cli_only_reads_supplied_files(tmp_path, monkeypatch, capsys):
    import socket
    import subprocess

    from market_intel_publication.agent_research_review import main

    baseline = report(tmp_path, "baseline", "2026-10-02")
    current = report(tmp_path, "current", "2026-10-05")

    def forbidden(*args, **kwargs):
        raise AssertionError("review cannot fetch, generate or send")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    args = [
        "--baseline",
        str(baseline[0]),
        "--baseline-manifest",
        str(baseline[1]),
        "--baseline-date",
        "2026-10-02",
        "--current",
        str(current[0]),
        "--current-manifest",
        str(current[1]),
        "--current-date",
        "2026-10-05",
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["report_kind"] == "us_daily"
