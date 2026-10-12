from __future__ import annotations

import subprocess
from pathlib import Path

from market_intel_commentary import generate_commentary


def test_codex_timeout_is_recorded_and_fallback_attempts_continue(
    monkeypatch, tmp_path: Path
) -> None:
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("codex", timeout=240)

    monkeypatch.setattr(generate_commentary, "run_codex", timeout)

    result = generate_commentary.run(
        tmp_path / "reports.json",
        tmp_path / "summaries.json",
        tmp_path / "insights.json",
        tmp_path / "archive",
        tmp_path / "work",
        codex_cli=Path("/usr/bin/codex"),
        provider_keys={},
    )

    assert result == {
        "status": "unavailable",
        "attempts": [
            {"provider": "codex", "status": "unavailable", "error_type": "TimeoutExpired"},
            {"provider": "deepseek", "status": "not_configured"},
            {"provider": "gemini", "status": "not_configured"},
            {"provider": "minimax", "status": "not_configured"},
        ],
    }
