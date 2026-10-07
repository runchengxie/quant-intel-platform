from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_export_site_snapshot_is_publicly_available_from_owner_package():
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    assert callable(export_site_snapshot)


def test_export_site_snapshot_rejects_output_inside_repository(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    with pytest.raises(ValueError, match="outside"):
        export_site_snapshot(tmp_path, tmp_path / "generated")


def _public_root(root: Path, reports: list[dict] | None = None) -> Path:
    public = root / "artifacts/public"
    (public / "data").mkdir(parents=True)
    (public / "data/reports.json").write_text(
        json.dumps(
            {
                "schema_version": "market_intel_pages.reports.v1",
                "generated_at": "2026-10-01T00:00:00+08:00",
                "reports": reports or [],
            }
        )
    )
    (public / "data/daily_summaries.json").write_text(
        json.dumps({"schema_version": "market_intel_pages.daily_summaries.v1", "summaries": []})
    )
    return public


def test_export_site_snapshot_copies_valid_indexes_without_html(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root, output = tmp_path / "pages", tmp_path / "output"
    _public_root(root)
    export_site_snapshot(root, output)

    assert json.loads((output / "data/reports.json").read_text())["reports"] == []
    assert json.loads((output / "data/health.json").read_text())["status"] == "missing"
    assert not (output / "index.html").exists()


def test_export_site_snapshot_ignores_charts_outside_the_public_report_window(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root, output = tmp_path / "pages", tmp_path / "output"
    public = _public_root(root)
    chart_dir = public / "data/charts"
    chart_dir.mkdir()
    stale_chart = chart_dir / "2026-09-24-evening.json"
    stale_chart.write_text(
        json.dumps({"report_id": "2026-09-24-evening", "publication": "private"})
    )

    export_site_snapshot(root, output)

    assert not (output / "data/charts/2026-09-24-evening.json").exists()


def test_export_site_snapshot_rejects_more_than_five_dates_and_keeps_old_output(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root, output = tmp_path / "pages", tmp_path / "output"
    public = _public_root(root)
    export_site_snapshot(root, output)
    prior = (output / "data/reports.json").read_bytes()
    reports = [
        {"id": f"2026-10-{day:02d}-evening", "date": f"2026-10-{day:02d}", "kind": "evening"}
        for day in range(1, 7)
    ]
    (public / "data/reports.json").write_text(
        json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": reports})
    )

    with pytest.raises(ValueError, match="five trading dates"):
        export_site_snapshot(root, output)
    assert (output / "data/reports.json").read_bytes() == prior


def test_export_site_snapshot_rejects_unsafe_report_path(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root = tmp_path / "pages"
    report = {
        "id": "2026-10-01-evening",
        "date": "2026-10-01",
        "kind": "evening",
        "source_url": "reports/../../private.md",
    }
    _public_root(root, [report])

    with pytest.raises(ValueError, match="invalid report source path"):
        export_site_snapshot(root, tmp_path / "output")


def test_export_site_snapshot_rejects_symlinked_chart_directory(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root = tmp_path / "pages"
    public = _public_root(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (public / "data/charts").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="unsafe public chart directory"):
        export_site_snapshot(root, tmp_path / "output")


def test_export_site_snapshot_emits_bound_us_status_and_preserves_report_bytes(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root, output = tmp_path / "pages", tmp_path / "output"
    public = _public_root(root)
    report = {
        "publication": "public",
        "run_id": "daily-2026-10-06",
        "content_hash": "a" * 64,
        "facts": [],
        "claims": [],
        "source_status": {},
        "sections": [],
    }
    source = public / "data/market_daily_report.json"
    source.write_text(json.dumps(report))
    export_site_snapshot(root, output)
    status = json.loads((output / "data/us_daily_status.json").read_text())
    assert status["reports"][0]["date"] == "2026-10-06"
    assert status["reports"][0]["content_hash"] == report["content_hash"]
    assert status["reports"][0]["report_status"]["market"] == "incomplete"
    assert (output / "data/market_daily_report.json").read_bytes() == source.read_bytes()
