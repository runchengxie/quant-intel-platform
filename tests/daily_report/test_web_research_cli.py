import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from daily_messenger import cli
from daily_messenger.daily_report import web_research

MARKET_DATE = date(2026, 9, 18)
CUTOFF = datetime(2026, 9, 19, 1, tzinfo=UTC)
VALID = {
    "candidates": [
        {
            "section": "market",
            "title": "US stock indexes finish mixed",
            "source_url": "https://example.org/market-close",
            "published_at": "2026-09-18T21:30:00+00:00",
            "observation_date": "2026-09-18",
            "summary": "US indexes ended mixed.",
            "supporting_passage": "Stocks closed mixed on Friday.",
            "phase": "close",
        }
    ]
}


def test_runner_requests_live_read_only_search_and_writes_review_draft(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(json.dumps(VALID), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(web_research.subprocess, "run", fake_run)
    artifact_path = web_research.run_web_research(
        MARKET_DATE, tmp_path, cutoff=CUTOFF, codex_bin="codex-test"
    )

    command = captured["command"]
    assert command[:3] == ["codex-test", "--search", "exec"]
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--output-schema" in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "2026-09-18" in command[-1]
    assert captured["kwargs"]["timeout"] <= 300
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["market_date"] == "2026-09-18"
    assert artifact["candidates"][0]["review_status"] == "needs_review"
    assert artifact["accepted_count"] == 1
    assert artifact["rejected"] == []
    receipt_path = tmp_path / "receipts" / artifact_path.name
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["artifact"] == artifact_path.name
    assert receipt["accepted_count"] == 1


def test_bad_output_does_not_overwrite_previous_draft(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(json.dumps(VALID), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(web_research.subprocess, "run", fake_run)
    first = web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF)
    original = first.read_bytes()

    def bad_run(command, **kwargs):
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text("not json", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(web_research.subprocess, "run", bad_run)
    with pytest.raises(web_research.WebResearchError, match="invalid JSON"):
        web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF)
    assert first.read_bytes() == original
    assert list(tmp_path.glob("web-research-*.json")) == [first]


def test_nonzero_codex_exit_is_reported_without_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(
        web_research.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 7, "", "secret stderr"),
    )
    with pytest.raises(web_research.WebResearchError, match="exit code 7"):
        web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF)
    assert list(tmp_path.glob("web-research-*.json")) == []


def test_output_must_be_outside_repository():
    with pytest.raises(web_research.WebResearchError, match="outside"):
        web_research.run_web_research(
            MARKET_DATE, Path(web_research.__file__).resolve().parents[3] / "out", cutoff=CUTOFF
        )


def test_research_cli_dispatches_requested_market_date_and_private_output(monkeypatch, tmp_path):
    called = {}

    def fake_research(market_date, output_dir, *, cutoff):
        called.update(date=market_date, output=output_dir, cutoff=cutoff)
        return tmp_path / "draft.json"

    monkeypatch.setattr(web_research, "run_web_research", fake_research)
    assert (
        cli.main(
            [
                "research",
                "--date",
                "2026-09-18",
                "--out",
                str(tmp_path),
                "--cutoff",
                "2026-09-19T01:00:00+00:00",
            ]
        )
        == 0
    )
    assert called["date"] == MARKET_DATE
    assert called["output"] == tmp_path
    assert called["cutoff"] == CUTOFF
