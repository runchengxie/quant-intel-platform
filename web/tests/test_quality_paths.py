"""Regression checks for CLI boundaries, provider failures, and archival inputs."""

import io
import json
import os
import runpy
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest
from test_build_site import create_site
from test_insight_provider import Response
from test_insights import analysis, sources

from scripts.generate_daily_summary import CHINA_TZ, report_generated_at, validate_summary
from scripts.generate_insights import _load_history, run
from scripts.import_reports import parse_markdown
from scripts.insight_contract import build_context, validate_analysis
from scripts.insight_provider import generate
from scripts.pipeline_health import health_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("colon", [":", "："])
@pytest.mark.parametrize("stamp", ["2026-09-19 12:30", "2026-09-19 12:30:47"])
def test_report_generation_time_accepts_existing_minutes_and_precise_backfill(colon, stamp):
    row = {"sections": [{"paragraphs": [f"生成时间{colon} {stamp}"]}]}
    assert report_generated_at(row) == datetime.fromisoformat(stamp).replace(tzinfo=CHINA_TZ)


@pytest.mark.parametrize("marker", ["", "报告生成方式: backfill", "报告生成方式： backfill"])
def test_import_preserves_explicit_backfill_provenance(marker):
    row = parse_markdown(
        f"# 晨报\n生成时间: 2026-09-19 12:30:47\n{marker}\n## 盘面\n数据已恢复。",
        "2026-09-18",
        "morning",
    )
    if marker:
        assert row["generation_mode"] == "backfill"
    else:
        assert "generation_mode" not in row


@pytest.mark.parametrize("backfill_index", [0, 1])
def test_recently_generated_backfill_is_still_retrospective(tmp_path, backfill_index):
    rows = sources()
    rows[backfill_index]["generation_mode"] = "backfill"
    reports = tmp_path / "reports.json"
    reports.write_text(json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows}))
    with patch("scripts.generate_insights.datetime", wraps=datetime) as clock:
        clock.now.return_value = datetime.fromisoformat("2026-09-15T07:00:30+08:00")
        result = run(reports, tmp_path / "insights.json", api_key="test", generator=lambda *args: analysis())
    note = result["insights"][0]
    assert note["generation_mode"] == "retrospective"
    assert note["as_of"] == "2026-09-15T07:00:00+08:00"


@pytest.mark.parametrize(
    ("target", "status", "days"),
    [
        ("2026-09-10", "stale", 9),
        ("2026-09-18", "calendar_unverified", 1),
        ("2026-09-20", "invalid_timestamp", -1),
    ],
)
def test_freshly_backfilled_report_does_not_hide_target_age(target, status, days):
    row = {
        "id": "m",
        "date": target,
        "kind": "morning",
        "sections": [{"paragraphs": ["生成时间: 2026-09-19 10:00:00"]}],
    }
    health = health_report({"reports": [row]}, now=datetime.fromisoformat("2026-09-19T11:00:00+08:00"))
    assert health["status"] == status
    assert health["latest_target_age_days"] == days
    assert health["source_age_hours"] == 1


def test_summary_whitespace_normalization_remains_compatible():
    assert validate_summary("继续观察。\n注意风险。") == "继续观察。 注意风险。"


@pytest.mark.parametrize("provider", ["gemini", "minimax"])
@pytest.mark.parametrize("failure", ["network", "server", "oversize"])
def test_provider_failures_are_bounded_and_do_not_expose_response(provider, failure):
    if failure == "network":
        effect = [URLError("connection failed") for _ in range(3)]
        expected = URLError
    elif failure == "server":
        effect = [
            HTTPError(
                "https://example.test/secret", 503, "private", {}, io.BytesIO(b"private server response")
            )
            for _ in range(3)
        ]
        expected = HTTPError
    else:

        class Oversized(Response):
            def read(self, size):
                assert size == 1_000_001
                return b"x" * size

        effect = [Oversized({})]
        expected = ValueError
    with patch("scripts.insight_provider.urlopen", side_effect=effect) as opened:
        with patch("scripts.insight_provider.time.sleep") as sleep:
            with pytest.raises(expected) as caught:
                generate({}, "prompt", provider, "test", "secret")
    assert opened.call_count == (1 if failure == "oversize" else 3)
    assert sleep.call_count == (0 if failure == "oversize" else 2)
    assert "private" not in str(caught.value)
    assert "secret" not in str(caught.value)


def test_deepseek_uses_json_object_mode():
    payload = {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok": true}'}}]}
    with patch("scripts.insight_provider.urlopen", return_value=Response(payload)) as opened:
        assert generate({}, "prompt", "deepseek", "deepseek-chat", "key") == {"ok": True}
    request = opened.call_args.args[0]
    assert "api.deepseek.com" in request.full_url
    assert json.loads(request.data)["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_minimax_decodes_fences_and_rejects_truncated_output(finish):
    payload = {
        "choices": [
            {
                "finish_reason": finish,
                "message": {"content": '<think>hidden</think>```json\n{"ok": true}\n```'},
            }
        ]
    }
    with patch("scripts.insight_provider.urlopen", return_value=Response(payload)):
        if finish == "stop":
            assert generate({}, "prompt", "minimax", "test", "key") == {"ok": True}
        else:
            with pytest.raises(ValueError, match="incomplete"):
                generate({}, "prompt", "minimax", "test", "key")


@pytest.mark.parametrize(
    ("context", "provider", "model", "message"),
    [
        ({"text": "x" * 120001}, "gemini", "test", "context"),
        ({}, "unknown", "test", "unsupported"),
        ({}, "gemini", "../secret", "identifier"),
    ],
)
def test_provider_rejects_invalid_request_before_network(context, provider, model, message):
    with patch("scripts.insight_provider.urlopen") as opened:
        with pytest.raises(ValueError, match=message):
            generate(context, "prompt", provider, model, "key")
    opened.assert_not_called()


@pytest.mark.parametrize("url", ["http://example.test/history", "file:///tmp/history"])
def test_history_requires_https_before_network(tmp_path, url):
    with pytest.raises(ValueError, match="HTTPS"):
        _load_history(tmp_path / "missing.json", url)


def test_unavailable_published_history_returns_a_warning(tmp_path):
    with patch("scripts.generate_insights.urlopen", side_effect=URLError("offline")):
        assert _load_history(tmp_path / "missing.json", "https://example.test/history") == (
            [],
            "published_history_unavailable",
        )


def test_published_history_is_loaded_only_for_matching_schema(tmp_path):
    valid = {"schema_version": "market_intel_pages.insights.v1", "insights": [{"id": "saved"}]}
    with patch("scripts.generate_insights.urlopen", return_value=Response(valid)):
        assert _load_history(tmp_path / "missing.json", "https://example.test/history") == (
            [{"id": "saved"}],
            None,
        )
    with patch("scripts.generate_insights.urlopen", return_value=Response({"schema_version": "unknown"})):
        assert _load_history(tmp_path / "missing.json", "https://example.test/history") == ([], None)


@pytest.mark.parametrize("field", ["overview", "changes", "tensions", "watchpoints"])
def test_malformed_analysis_is_rejected(field):
    rows = sources()
    payload = analysis()
    payload[field] = None
    with pytest.raises(ValueError):
        validate_analysis(payload, build_context(rows, rows[1], rows[0]))


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    create_site(root)
    index_path = root / "artifacts/public/data/reports.json"
    data = json.loads(index_path.read_text())
    for row in data["reports"]:
        hour = "07:00:00" if row["kind"] == "morning" else "19:00:00"
        row["sections"] = [{"paragraphs": [f"生成时间: {row['date']} {hour}"]}]
    index_path.write_text(json.dumps(data))
    return root


def invoke(script, arguments):
    with patch.object(sys, "argv", [script, *map(str, arguments)]):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
                runpy.run_path(str(ROOT / "scripts" / script), run_name="__main__")


def test_snapshot_build_and_health_cli_use_real_temporary_files(site, tmp_path):
    archive = tmp_path / "archive"
    invoke("sync_public_snapshot.py", ["--root", site, "--archive-dir", archive])
    output = tmp_path / "output"
    invoke("build_site.py", ["--root", site, "--output", output])
    assert len(json.loads((output / "data/reports.json").read_text())["reports"]) == 10
    health = tmp_path / "health.json"
    with pytest.raises(SystemExit) as exit_status:
        invoke(
            "pipeline_health.py",
            [
                "--reports",
                site / "artifacts/public/data/reports.json",
                "--output",
                health,
                "--expected-date",
                "2099-01-01",
                "--strict",
            ],
        )
    assert exit_status.value.code == 2
    assert json.loads(health.read_text())["status"] == "behind"


def test_generation_and_comparison_clis_without_credentials(site, tmp_path):
    reports = site / "artifacts/public/data/reports.json"
    summaries = tmp_path / "summaries.json"
    with pytest.raises(SystemExit) as exit_status:
        invoke(
            "generate_daily_summary.py",
            [
                "--reports",
                reports,
                "--summaries",
                site / "artifacts/public/data/daily_summaries.json",
                "--output",
                summaries,
            ],
        )
    assert exit_status.value.code == 0
    assert summaries.is_file()
    insights = tmp_path / "insights.json"
    invoke("generate_insights.py", ["--reports", reports, "--output", insights])
    assert json.loads(insights.read_text())["generation"]["status"] in {"not_configured", "no_source_pair"}
    comparison = tmp_path / "comparison"
    invoke("compare_models.py", ["--reports", reports, "--output-dir", comparison])
    assert len(json.loads((comparison / "comparison.json").read_text())["runs"]) == 3


def test_import_cli_preview_never_changes_the_public_snapshot(site, tmp_path):
    source = tmp_path / "incoming.md"
    source.write_text("# 新报\n生成时间: 2026-09-19 12:00:00\n## 盘面\n新内容。")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "market_intel_pages.import.v1",
                "publication": "public",
                "reports": [{"path": source.name, "date": "2026-09-18", "kind": "evening"}],
            }
        )
    )
    before = (site / "artifacts/public/data/reports.json").read_bytes()
    invoke(
        "import_reports.py", ["--root", site, "--manifest", manifest, "--archive-dir", tmp_path / "archive"]
    )
    assert (site / "artifacts/public/data/reports.json").read_bytes() == before
    assert not (tmp_path / "archive").exists()
