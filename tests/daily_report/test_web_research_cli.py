import json
import subprocess
import traceback
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


def test_single_section_is_bounded_and_still_needs_review(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        captured["prompt"] = command[-1]
        Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(VALID))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(web_research.subprocess, "run", fake_run)
    artifact = web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF, section="market")
    assert captured["timeout"] == 180
    assert "Only research section market" in captured["prompt"]
    assert "at most two" in captured["prompt"]
    result = json.loads(artifact.read_text())
    assert result["section"] == "market"
    receipt = json.loads((tmp_path / "receipts" / artifact.name).read_text())
    assert result["timeout_seconds"] == receipt["timeout_seconds"] == 180
    assert result["candidates"][0]["review_status"] == "needs_review"


@pytest.mark.parametrize(
    "rows", [[{**VALID["candidates"][0], "section": "macro"}], VALID["candidates"] * 3]
)
def test_single_section_rejects_out_of_scope_payload(monkeypatch, tmp_path, rows):
    def fake_run(command, **kwargs):
        Path(command[command.index("--output-last-message") + 1]).write_text(
            json.dumps({"candidates": rows})
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(web_research.subprocess, "run", fake_run)
    with pytest.raises(web_research.WebResearchError, match="section bounds"):
        web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF, section="market")
    assert not list(tmp_path.glob("web-research-*.json"))


def test_section_cli_forwards_selected_topic(monkeypatch, tmp_path):
    captured = {}

    def fake_research(market_date, output, *, cutoff, section):
        captured["section"] = section
        return output / "draft.json"

    monkeypatch.setattr(web_research, "run_web_research", fake_research)
    assert (
        cli.main(["research", "--date", "2026-09-18", "--out", str(tmp_path), "--section", "macro"])
        == 0
    )
    assert captured["section"] == "macro"


def test_section_timeout_keeps_no_success_artifact(monkeypatch, tmp_path):
    def fail(command, **kwargs):
        assert kwargs["timeout"] == 180
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(web_research.subprocess, "run", fail)
    with pytest.raises(web_research.WebResearchError, match="timed out"):
        web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF, section="macro")
    assert not list(tmp_path.glob("web-research-*.json"))


@pytest.mark.parametrize("section,budget", [("market", 600), ("market", 30), (None, 300)])
def test_explicit_research_budget_is_applied_and_recorded(monkeypatch, tmp_path, section, budget):
    def fake_run(command, **kwargs):
        assert kwargs["timeout"] == budget
        Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(VALID))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(web_research.subprocess, "run", fake_run)
    artifact = web_research.run_web_research(
        MARKET_DATE, tmp_path, cutoff=CUTOFF, section=section, timeout_seconds=budget
    )
    result = json.loads(artifact.read_text())
    receipt = json.loads((tmp_path / "receipts" / artifact.name).read_text())
    assert result["timeout_seconds"] == receipt["timeout_seconds"] == budget
    assert result["review_status"] == "needs_review"


@pytest.mark.parametrize("budget", [0, 29, 601, True, 180.5])
def test_invalid_budget_is_rejected_before_creating_output(monkeypatch, tmp_path, budget):
    def fail(command, **kwargs):
        pytest.fail("invalid budget must not launch Codex")

    monkeypatch.setattr(web_research.subprocess, "run", fail)
    output = tmp_path / "not-created"
    with pytest.raises(web_research.WebResearchError, match="timeout"):
        web_research.run_web_research(MARKET_DATE, output, cutoff=CUTOFF, timeout_seconds=budget)
    assert not output.exists()


def test_cli_explicit_budget_reaches_research(monkeypatch, tmp_path):
    def fake_research(market_date, output, **kwargs):
        assert kwargs["section"] == "company_news"
        assert kwargs["timeout_seconds"] == 300
        return output / "draft.json"

    monkeypatch.setattr(web_research, "run_web_research", fake_research)
    assert (
        cli.main(
            [
                "research",
                "--date",
                "2026-09-18",
                "--out",
                str(tmp_path),
                "--section",
                "company_news",
                "--timeout-seconds",
                "300",
            ]
        )
        == 0
    )


@pytest.mark.parametrize("budget", ["29", "601"])
def test_cli_invalid_budget_leaves_no_output(monkeypatch, tmp_path, budget):
    def fail(command, **kwargs):
        pytest.fail("invalid budget must not launch Codex")

    monkeypatch.setattr(web_research.subprocess, "run", fail)
    output = tmp_path / "not-created"
    assert (
        cli.main(
            ["research", "--date", "2026-09-18", "--out", str(output), "--timeout-seconds", budget]
        )
        == 2
    )
    assert not output.exists()


def test_runner_requests_live_read_only_search_and_writes_review_draft(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        captured["schema"] = json.loads(
            Path(command[command.index("--output-schema") + 1]).read_text()
        )
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
    assert command[command.index("-c") + 1] == "model_reasoning_effort=medium"
    assert "--output-schema" in command
    properties = captured["schema"]["properties"]["candidates"]["items"]["properties"]
    assert "null" in properties["published_at"]["type"]
    assert properties["publication_precision"]["enum"] == ["timestamp", "date"]
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "2026-09-18" in command[-1]
    assert "company investor-relations releases" in command[-1]
    assert "after-close market drivers" in command[-1]
    assert "sector leadership and market breadth" in command[-1]
    assert "dollar, yen, gold, silver, crude oil, and bitcoin" in command[-1]
    assert "upcoming economic releases and Federal Reserve events" in command[-1]
    assert "company-specific catalyst" in command[-1]
    assert "same accessible page supports both" in command[-1]
    assert "separate single-source candidates" in command[-1]
    assert "published before the cutoff" in command[-1]
    assert "do not fill a quota" in command[-1]
    assert "at least three distinct company-news candidates" in command[-1]
    assert "natural Chinese" in command[-1]
    assert captured["kwargs"]["timeout"] == 480
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["market_date"] == "2026-09-18"
    assert artifact["candidates"][0]["review_status"] == "needs_review"
    assert artifact["accepted_count"] == 1
    assert artifact["rejected"] == []
    receipt_path = tmp_path / "receipts" / artifact_path.name
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["artifact"] == artifact_path.name
    assert receipt["accepted_count"] == 1
    assert receipt["cutoff"] == CUTOFF.isoformat()
    assert receipt["model"] == artifact["model"]
    assert receipt["reasoning_effort"] == artifact["reasoning_effort"] == "medium"
    assert receipt["timeout_seconds"] == artifact["timeout_seconds"] == 480
    assert receipt["rejected"] == []


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


def test_codex_failure_reports_sanitized_stderr_tail(monkeypatch, tmp_path):
    monkeypatch.setattr(
        web_research.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            "",
            "ERROR upstream denied api_key=do-not-log-this\nconnection refused",
        ),
    )

    with pytest.raises(web_research.WebResearchError) as error:
        web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF)

    assert "exit code 1" in str(error.value)
    assert "connection refused" in str(error.value)
    assert "do-not-log-this" not in str(error.value)


def test_timeout_preserves_earlier_draft(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(json.dumps(VALID), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(web_research.subprocess, "run", fake_run)
    first = web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF)

    def timed_out(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(web_research.subprocess, "run", timed_out)
    with pytest.raises(web_research.WebResearchError, match="timed out"):
        web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF)
    assert list(tmp_path.glob("web-research-*.json")) == [first]


def test_output_must_be_outside_repository():
    with pytest.raises(web_research.WebResearchError, match="outside"):
        web_research.run_web_research(
            MARKET_DATE, Path(web_research.__file__).resolve().parents[3] / "out", cutoff=CUTOFF
        )


@pytest.mark.parametrize(
    "stderr,routing,search",
    [
        (b"ERROR workspace routing discovery failed api_key=secret", True, False),
        ("tool web.run searching token=secret", False, True),
        (b"\xff workspace routing discovery failed; web search; api_key=secret", True, True),
        (None, False, False),
    ],
)
def test_timeout_reports_activity_flags_without_raw_logs(
    monkeypatch, tmp_path, stderr, routing, search
):
    def timed_out(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr=stderr)

    monkeypatch.setattr(web_research.subprocess, "run", timed_out)
    with pytest.raises(web_research.WebResearchError) as error:
        web_research.run_web_research(MARKET_DATE, tmp_path, cutoff=CUTOFF)
    message = str(error.value)
    assert f"routing_failure_observed={str(routing).lower()}" in message
    assert f"search_activity_observed={str(search).lower()}" in message
    assert "secret" not in message
    assert "secret" not in "".join(traceback.format_exception(error.value))
    assert list(tmp_path.glob("web-research-*.json")) == []


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
