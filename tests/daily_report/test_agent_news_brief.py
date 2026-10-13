import json
from pathlib import Path

import pytest

from market_intel_publication.agent_market_brief import main, read_market_brief
from tests.daily_report.test_news_revision import inputs, revision


def test_news_brief_requires_parent_and_preserves_date_precision(tmp_path):
    paths = inputs(tmp_path)
    revised = revision(paths, tmp_path / "stage").artifact_path
    manifest = revised.parent / "publication.json"
    with pytest.raises(ValueError, match="immutable original"):
        read_market_brief(revised, manifest, expected_date="2026-10-02")
    result = read_market_brief(
        revised, manifest, expected_date="2026-10-02", previous_report=paths[0]
    )
    assert result["report"]["schema_version"] == "1.1"
    event = result["report"]["events"][0]
    assert event["source_time"] is None
    assert event["publication_precision"] == "date"
    assert event["source_url"]
    assert result["report"]["claims"][0]["evidence_ids"] == [event["id"]]


def test_news_brief_cli_has_no_external_side_effects(tmp_path, capsys, monkeypatch):
    import socket
    import subprocess

    paths = inputs(tmp_path)
    revised = revision(paths, tmp_path / "stage").artifact_path

    def forbidden(*args, **kwargs):
        raise AssertionError("brief must only read the supplied bundle")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert (
        main(
            [
                "--input",
                str(revised),
                "--manifest",
                str(revised.parent / "publication.json"),
                "--expected-date",
                "2026-10-02",
                "--previous-report",
                str(paths[0]),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["report_date"] == "2026-10-02"


def test_news_brief_parses_and_hashes_one_parent_snapshot(tmp_path, monkeypatch):
    paths = inputs(tmp_path)
    revised = revision(paths, tmp_path / "stage").artifact_path
    parent = paths[0]
    original = parent.read_bytes()
    reader = Path.read_bytes
    reads = 0

    def replacing_reader(path):
        nonlocal reads
        if path == parent:
            reads += 1
            return original if reads == 1 else b"{}"
        return reader(path)

    monkeypatch.setattr(Path, "read_bytes", replacing_reader)
    read_market_brief(
        revised,
        revised.parent / "publication.json",
        expected_date="2026-10-02",
        previous_report=parent,
    )
    assert reads == 1
