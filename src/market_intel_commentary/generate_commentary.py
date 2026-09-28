"""Generate verified commentary with Codex first and configured API fallbacks."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from .generate_codex_commentary import run as run_codex
from .generate_daily_summary import run as run_summary
from .generate_insights import DEFAULT_MODELS
from .generate_insights import run as run_insight

FALLBACK_ORDER = ("deepseek", "gemini", "minimax")


def _try_codex(  # noqa: PLR0913 - preserve tested migration interface
    reports: Path, summaries: Path, insights: Path, archive: Path, work_dir: Path, cli: Path
) -> dict[str, str]:
    try:
        status = run_codex(reports, summaries, insights, archive, work_dir, cli)
        return {"provider": "codex", "status": status}
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        attempt = {"provider": "codex", "status": "unavailable", "error_type": type(exc).__name__}
        if isinstance(exc, RuntimeError):
            match = re.fullmatch(
                r"codex_exit_\d+:(authentication|rate_limit|network|unknown)", str(exc)
            )
            if match:
                attempt["error_code"] = match.group(1)
        return attempt


def run(  # noqa: PLR0913 - preserve tested migration interface
    reports: Path,
    summaries: Path,
    insights: Path,
    archive: Path,
    work_dir: Path,
    *,
    codex_cli: Path | None,
    provider_keys: dict[str, list[str]],
) -> dict:
    attempts: list[dict[str, str]] = []
    if codex_cli is not None:
        attempts.append(_try_codex(reports, summaries, insights, archive, work_dir, codex_cli))
        if attempts[-1]["status"].startswith(("generated", "reused")):
            return {"status": "ready", "provider": "codex", "attempts": attempts}
    for provider in FALLBACK_ORDER:
        keys = [key for key in provider_keys.get(provider, []) if key]
        if not keys:
            attempts.append({"provider": provider, "status": "not_configured"})
            continue
        try:
            result = run_insight(
                reports,
                insights,
                provider=provider,
                model=os.environ.get(f"{provider.upper()}_MODEL") or DEFAULT_MODELS[provider],
                api_key=keys,
                history_path=insights,
                archive_dir=archive,
            )
            generation = result["generation"]
            attempts.append({"provider": provider, "status": generation["status"]})
            if generation["status"] not in {"generated", "cached"}:
                continue
            summary_status = run_summary(
                reports,
                summaries,
                summaries,
                None,
                insights_path=insights,
            )
            if summary_status in {"generated summary", "reused existing summary"}:
                return {"status": "ready", "provider": provider, "attempts": attempts}
            attempts.append({"provider": provider, "status": "summary_unavailable"})
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            attempts.append(
                {"provider": provider, "status": "unavailable", "error_type": type(exc).__name__}
            )
    return {"status": "unavailable", "attempts": attempts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--summaries", type=Path, required=True)
    parser.add_argument("--insights", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--codex-cli", type=Path)
    args = parser.parse_args()
    keys = {
        provider: [os.environ.get(f"{provider.upper()}_API_KEY", "")] for provider in FALLBACK_ORDER
    }
    keys["gemini"].extend(os.environ.get(f"GEMINI_API_KEY_{index}", "") for index in (2, 3))
    result = run(
        args.reports,
        args.summaries,
        args.insights,
        args.archive_dir,
        args.work_dir,
        codex_cli=args.codex_cli,
        provider_keys=keys,
    )
    print(json.dumps(result, ensure_ascii=False))
    # Commentary is optional; return typed diagnostics to the private receipt.
    # A missing model must not prevent verified market facts from publishing.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
