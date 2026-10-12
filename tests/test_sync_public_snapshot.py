"""Exercise snapshot retention and validation before archive mutation."""

import json
import subprocess
import sys

import pytest

from market_intel_publication.sync_public_snapshot import sync_snapshot

REPORT_SCHEMA = "market_intel_pages.reports.v1"
SUMMARY_SCHEMA = "market_intel_pages.daily_summaries.v1"


def write_index(directory, name, records):
    filename = "daily_summaries" if name == "summaries" else name
    path = directory / "data" / f"{filename}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = REPORT_SCHEMA if name == "reports" else SUMMARY_SCHEMA
    path.write_text(json.dumps({"schema_version": schema, name: records}), encoding="utf-8")


def report(date):
    identity = f"{date}-morning"
    return {"id": identity, "date": date, "kind": "morning", "source_url": f"reports/{identity}.md"}


def write_report(directory, row, text):
    path = directory / row["source_url"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def snapshot(directory):
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    "invalid",
    [
        "summary",
        "archive_schema",
        "archive_markdown",
        "incoming_markdown",
        "duplicate_id",
        "archive_nested",
        "archive_suffix",
    ],
)
def test_invalid_snapshot_preserves_public_and_archive(tmp_path, invalid):
    root, archive = tmp_path / "repository", tmp_path / "archive"
    public = root / "artifacts/public"
    current, older = report("2026-10-12"), report("2026-10-09")
    if invalid == "archive_nested":
        older["source_url"] = "reports/nested/older.md"
    elif invalid == "archive_suffix":
        older["source_url"] = "reports/older.txt"
    write_index(public, "reports", [current])
    write_index(public, "summaries", [])
    write_report(public, current, "replacement")
    write_index(archive, "reports", [current, older])
    write_index(archive, "summaries", [])
    write_report(archive, current, "archived original")
    write_report(archive, older, "older original")
    if invalid == "summary":
        write_index(
            public,
            "summaries",
            [
                {
                    "date": current["date"],
                    "morning_report_id": current["id"],
                    "evening_report_id": "missing",
                }
            ],
        )
    elif invalid == "archive_schema":
        (archive / "data/reports.json").write_text(
            '{"schema_version": "unknown", "reports": []}', encoding="utf-8"
        )
    elif invalid == "archive_markdown":
        (archive / older["source_url"]).unlink()
    elif invalid == "incoming_markdown":
        write_index(public, "reports", [current, older])
    elif invalid == "duplicate_id":
        write_report(public, older, "valid final duplicate")
        missing = {**older, "source_url": "reports/missing.md"}
        write_index(public, "reports", [current, missing, older])
    before_public, before_archive = snapshot(public), snapshot(archive)
    errors = {
        "summary": "summary source report is missing",
        "archive_schema": "unsupported reports index",
        "archive_markdown": "archived report Markdown is missing",
        "incoming_markdown": "report Markdown is missing",
        "duplicate_id": "report Markdown is missing",
        "archive_nested": "invalid report source path",
        "archive_suffix": "invalid report source path",
    }
    with pytest.raises(ValueError, match=errors[invalid]):
        sync_snapshot(root, archive)
    assert snapshot(public) == before_public
    assert snapshot(archive) == before_archive


def test_cli_archives_all_dates_and_retains_five_idempotently(tmp_path):
    root, archive = tmp_path / "repository", tmp_path / "archive"
    public = root / "artifacts/public"
    rows = [report(f"2026-10-{day:02d}") for day in range(1, 7)]
    write_index(public, "reports", rows)
    write_index(public, "summaries", [])
    for row in rows:
        write_report(public, row, row["id"])
    command = [
        sys.executable,
        "-m",
        "market_intel_publication.sync_public_snapshot",
        "--root",
        str(root),
        "--archive-dir",
        str(archive),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    assert len(json.loads((archive / "data/reports.json").read_text())["reports"]) == 6
    retained = json.loads((public / "data/reports.json").read_text())["reports"]
    assert retained == rows[1:]
    assert not (public / rows[0]["source_url"]).exists()
    for row in rows:
        assert (archive / row["source_url"]).read_text() == row["id"]
    before_public, before_archive = snapshot(public), snapshot(archive)
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode == 0, second.stderr
    assert snapshot(public) == before_public
    assert snapshot(archive) == before_archive
