"""The private publisher uses the same Codex-first fallback contract."""

from pathlib import Path
from unittest.mock import patch

from scripts.generate_commentary import run


def paths() -> tuple[Path, Path, Path, Path, Path]:
    return tuple(
        Path(f"/private/{name}.json") for name in ("reports", "summaries", "insights", "archive", "work")
    )


@patch("scripts.generate_commentary.run_summary", return_value="generated summary")
@patch("scripts.generate_commentary.run_insight")
@patch("scripts.generate_commentary.run_codex", side_effect=RuntimeError("codex_exit_1:network"))
def test_deepseek_replaces_failed_codex(codex, insight, summary):
    insight.return_value = {"generation": {"status": "generated"}}
    result = run(*paths(), codex_cli=Path("/usr/bin/codex"), provider_keys={"deepseek": ["secret"]})
    assert result["status"] == "ready"
    assert result["provider"] == "deepseek"
    assert result["attempts"][0] == {
        "provider": "codex",
        "status": "unavailable",
        "error_type": "RuntimeError",
        "error_code": "network",
    }
    assert insight.call_args.kwargs["api_key"] == ["secret"]
    assert summary.called
    assert codex.called


@patch("scripts.generate_commentary.run_insight")
@patch("scripts.generate_commentary.run_codex", return_value="generated validated Codex commentary")
def test_codex_success_does_not_call_fallback(codex, insight):
    result = run(*paths(), codex_cli=Path("/usr/bin/codex"), provider_keys={"deepseek": ["secret"]})
    assert result["provider"] == "codex"
    insight.assert_not_called()
    assert codex.called


@patch("scripts.generate_commentary.run_insight")
def test_missing_keys_have_safe_diagnostics(insight):
    result = run(*paths(), codex_cli=None, provider_keys={})
    assert result["status"] == "unavailable"
    assert all(item["status"] == "not_configured" for item in result["attempts"])
    insight.assert_not_called()
