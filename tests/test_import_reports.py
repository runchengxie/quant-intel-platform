from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_intel_publication.import_reports import import_reports


def _write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def test_apply_rejects_invalid_archive_index_before_writing_revision_history(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    archive = tmp_path / "archive"
    public = root / "artifacts/public"
    index = {"schema_version": "market_intel_pages.reports.v1", "reports": []}
    _write(public / "data/reports.json", json.dumps(index))
    (public / "reports").mkdir(parents=True)
    _write(
        public / "data/daily_summaries.json",
        json.dumps({"schema_version": "market_intel_pages.daily_summaries.v1", "summaries": []}),
    )
    _write(
        archive / "data/reports.json", json.dumps({"schema_version": "unsupported", "reports": []})
    )
    source = _write(
        tmp_path / "source/2026-09-01.md",
        "# Morning report\n\n## Overview\n生成时间：2026-09-01 08:00\nMarket opened.\n",
    )
    manifest = _write(
        tmp_path / "source/manifest.json",
        json.dumps(
            {
                "schema_version": "market_intel_pages.import.v1",
                "publication": "public",
                "reports": [{"date": "2026-09-01", "kind": "morning", "path": source.name}],
            }
        ),
    )
    public_index_before = (public / "data/reports.json").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported reports index"):
        import_reports(root, manifest, archive, apply=True)

    assert (public / "data/reports.json").read_text(encoding="utf-8") == public_index_before
    assert not (archive / "report_revisions").exists()
