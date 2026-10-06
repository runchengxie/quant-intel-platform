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


def test_export_site_snapshot_copies_reviewed_chart_and_us_daily_history(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    from tests.test_chart_contract import public_chart

    root, output = tmp_path / "pages", tmp_path / "output"
    row = {
        "id": "2026-09-18-morning",
        "date": "2026-09-18",
        "kind": "morning",
        "source_url": "reports/2026-09-18-morning.md",
    }
    public = _public_root(root, [row])
    (public / row["source_url"]).parent.mkdir(parents=True)
    (public / row["source_url"]).write_text("# reviewed report\n")
    chart_dir = public / "data/charts"
    chart_dir.mkdir()
    (chart_dir / f"{row['id']}.json").write_text(json.dumps(public_chart()))
    daily = {"run_id": "daily-2026-09-18", "report_formats": ["md", "txt"]}
    (public / "data/market_daily_report.json").write_text(json.dumps(daily))
    (public / "data/market_daily_reports.json").write_text(
        json.dumps({"schema_version": "market_intel_pages.us_daily_history.v1", "reports": [daily]})
    )
    (public / "reports/2026-09-18-market-daily.md").write_text("# daily\n")
    (public / "reports/2026-09-18-market-daily.txt").write_text("daily\n")

    export_site_snapshot(root, output)

    assert (output / f"data/charts/{row['id']}.json").is_file()
    assert json.loads((output / "data/market_daily_reports.json").read_text())["reports"] == [daily]
    assert (output / "reports/2026-09-18-market-daily.txt").is_file()


def test_export_site_snapshot_exports_only_matching_public_asia_news(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    from tests.test_asia_news_import import news_fixture

    root, output = tmp_path / "pages", tmp_path / "output"
    text = "# 收盘复盘\n生成时间: 2026-09-30 20:00\n## 盘面\n上涨 2567 家。\n"
    row = {
        "id": "2026-09-30-evening",
        "date": "2026-09-30",
        "kind": "evening",
        "source_url": "reports/2026-09-30-evening.md",
    }
    public = _public_root(root, [row])
    (public / row["source_url"]).parent.mkdir(parents=True)
    (public / row["source_url"]).write_text(text)
    news = news_fixture(text)
    row["asia_news_sha256"] = news["content_sha256"]
    (public / "data/reports.json").write_text(
        json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": [row]})
    )
    (public / "data/asia_news").mkdir()
    (public / f"data/asia_news/{row['id']}.json").write_text(json.dumps(news))

    export_site_snapshot(root, output)

    projected = json.loads((output / f"data/asia_news/{row['id']}.json").read_text())
    assert projected["content_sha256"] == row["asia_news_sha256"]


def test_export_site_snapshot_rejects_invalid_index_and_keeps_previous_output(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root, output = tmp_path / "pages", tmp_path / "output"
    public = _public_root(root)
    export_site_snapshot(root, output)
    previous = (output / "data/reports.json").read_bytes()
    (public / "data/reports.json").write_text(json.dumps({"schema_version": "future", "reports": []}))

    with pytest.raises(ValueError, match="unsupported reports index"):
        export_site_snapshot(root, output)
    assert (output / "data/reports.json").read_bytes() == previous


def test_export_site_snapshot_accepts_us_latest_without_history_index(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root, output = tmp_path / "pages", tmp_path / "output"
    public = _public_root(root)
    row = {"run_id": "daily-2026-10-01", "report_formats": []}
    (public / "data/market_daily_report.json").write_text(json.dumps(row))
    (public / "reports").mkdir()
    (public / "reports/2026-10-01-market-daily.md").write_text("# daily\n")

    export_site_snapshot(root, output)

    assert json.loads((output / "data/market_daily_report.json").read_text()) == row
    assert (output / "reports/2026-10-01-market-daily.md").is_file()


def test_export_site_snapshot_rejects_missing_indexed_asia_news(tmp_path):
    from market_intel_publication.export_site_snapshot import export_site_snapshot

    root = tmp_path / "pages"
    row = {
        "id": "2026-09-30-evening",
        "date": "2026-09-30",
        "kind": "evening",
        "source_url": "reports/2026-09-30-evening.md",
        "asia_news_sha256": "a" * 64,
    }
    public = _public_root(root, [row])
    (public / row["source_url"]).parent.mkdir(parents=True)
    (public / row["source_url"]).write_text("# report\n")

    with pytest.raises(ValueError, match="indexed Asia news missing"):
        export_site_snapshot(root, tmp_path / "output")


def test_export_site_snapshot_cli_writes_requested_output(tmp_path, monkeypatch, capsys):
    import sys

    from market_intel_publication.export_site_snapshot import main

    root, output = tmp_path / "pages", tmp_path / "output"
    _public_root(root)
    monkeypatch.setattr(
        sys,
        "argv",
        ["market-export-site-snapshot", "--root", str(root), "--output", str(output)],
    )

    main()

    assert (output / "data/reports.json").is_file()
    assert f"Exported public report snapshot at {output}" in capsys.readouterr().out
