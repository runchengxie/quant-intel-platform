"""Private, review-required research candidates from public web reporting."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, date, datetime, time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

SECTIONS = frozenset({"market", "drivers", "macro", "company_news", "gainers", "losers"})
NEW_YORK = ZoneInfo("America/New_York")
FIELDS = (
    "section",
    "title",
    "source_url",
    "published_at",
    "observation_date",
    "summary",
    "supporting_passage",
    "phase",
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL = "gpt-6-sol"
CODEX_TIMEOUT_SECONDS = 480


class WebResearchError(RuntimeError):
    """The private research draft could not be generated safely."""


def _valid_source_url(source_url: object) -> bool:
    if not isinstance(source_url, str):
        return False
    try:
        parsed_url = urlsplit(source_url)
        return parsed_url.scheme in {"http", "https"} and bool(parsed_url.hostname)
    except ValueError:
        return False


def _source_reason(row: object, market_date: date, cutoff: datetime) -> str | None:
    if not isinstance(row, dict):
        return "invalid_candidate"
    values = cast("dict[str, object]", row)
    section = values.get("section")
    if not isinstance(section, str) or section not in SECTIONS:
        return "invalid_section"
    if values.get("observation_date") != market_date.isoformat():
        return "observation_date_mismatch"
    source_url = values.get("source_url")
    if not _valid_source_url(source_url):
        return "invalid_source_url"
    published_at = values.get("published_at")
    if not isinstance(published_at, str):
        return "invalid_published_at"
    try:
        source_time = datetime.fromisoformat(published_at)
    except ValueError:
        return "invalid_published_at"
    if source_time.tzinfo is None or source_time.utcoffset() is None:
        return "invalid_published_at"
    if source_time > cutoff:
        return "source_after_cutoff"
    phase = values.get("phase")
    if not isinstance(phase, str) or phase not in {"close", "intraday", "event"}:
        return "invalid_phase"
    market_close = datetime.combine(market_date, time(16), tzinfo=NEW_YORK)
    if values.get("phase") == "close" and source_time < market_close:
        return "preclose_source"
    return None


def _reason(row: object, market_date: date, cutoff: datetime) -> str | None:
    source_reason = _source_reason(row, market_date, cutoff)
    if source_reason:
        return source_reason
    assert isinstance(row, dict)
    values = cast("dict[str, object]", row)
    title = values.get("title")
    if not isinstance(title, str) or not title.strip():
        return "missing_title"
    summary = values.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return "missing_summary"
    passage = values.get("supporting_passage")
    if not isinstance(passage, str) or not passage.strip():
        return "missing_support"
    if len(passage) > 160:
        return "support_too_long"
    return None


def validate_candidates(
    payload: object, *, market_date: date, cutoff: datetime
) -> tuple[list[dict[str, str]], list[str]]:
    """Check structural and point-in-time boundaries; accepted rows still need review."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")
    if not isinstance(payload, dict):
        return [], ["invalid_payload"]
    rows = cast("dict[str, object]", payload).get("candidates")
    if not isinstance(rows, list):
        return [], ["invalid_payload"]
    accepted: list[dict[str, str]] = []
    rejected: list[str] = []
    for index, row in enumerate(rows):
        reason = _reason(row, market_date, cutoff)
        if reason:
            rejected.append(f"candidate[{index}]:{reason}")
            continue
        assert isinstance(row, dict)
        values = cast("dict[str, str]", row)
        candidate: dict[str, str] = {field: values[field].strip() for field in FIELDS}
        candidate["review_status"] = "needs_review"
        accepted.append(candidate)
    return accepted, rejected


def _output_schema() -> dict[str, object]:
    properties = {field: {"type": "string"} for field in FIELDS}
    return {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(FIELDS),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidates"],
        "additionalProperties": False,
    }


def _prompt(market_date: date, cutoff: datetime) -> str:
    return (
        "Search the live public web for a private US market daily-report research draft. "
        f"Target US trading/observation date: {market_date.isoformat()}. "
        f"Source publication cutoff: {cutoff.isoformat()}. "
        "Find and open original webpages, not only search snippets. Consider six sections: market, "
        "drivers, macro, company_news, gainers, losers. Prioritize company investor-relations releases, "
        "regulatory filings, and accessible original reporting for company_news; seek several distinct "
        "companies, not several rewrites of one event. For after-close market drivers, prefer full "
        "closing-wrap reports; separate observed moves from a source's attributed interpretation. "
        "Search independently for sector leadership and market breadth, including equal-weight versus "
        "capitalization-weighted performance when a dated source provides both figures. Check the "
        "dollar, yen, gold, silver, crude oil, and bitcoin for dated close or settlement reports; "
        "state the instrument and session explicitly and do not mix intraday snapshots with closes. "
        "For macro, look for actual, consensus, prior, and revisions only when the original release "
        "or a fully accessible report supports each number; also look for upcoming economic releases "
        "and Federal Reserve events that were already announced and published before the cutoff, "
        "giving the future event date in the summary. For movers, look for a verified closing move "
        "and a separately attributed company-specific catalyst, including filings, earnings guidance, "
        "or analyst rating changes. Combine a move and catalyst in one candidate only when the same "
        "accessible page supports both; if the pages differ, return separate single-source candidates "
        "without asserting a causal link. Never infer the catalyst solely from price action. "
        "A midday article may support an intraday event but not a closing explanation. Search across "
        "these sections, but do not fill a quota: return fewer items if original evidence is thin. "
        "Treat snippets, aggregators, and paywall teasers only as discovery leads; omit any item "
        "whose original page cannot be opened and checked. Return JSON matching the provided schema only. "
        "For each candidate, supply the original HTTP(S) source_url, source article title, "
        "timezone-aware published_at, explicit observation_date, a short original paraphrase "
        "in summary, and supporting_passage of at most 160 characters. "
        "Set phase to close, intraday, or event. A close item needs an article published after "
        "the 4 p.m. New York cash close for that observation date; never label a midday item as close. "
        "Do not infer a market date from the publication date. Do not invent timestamps, numbers, "
        "URLs, ratings, or causes. Attribute interpretations to their source. If provenance is "
        "unclear, omit the candidate. An empty array is valid. "
        "Do not give investment advice or copy whole article paragraphs."
    )


def _minimal_codex_env() -> dict[str, str]:
    allowed = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TERM",
        "CODEX_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "SSL_CERT_FILE",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def _write_unique_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_web_research(
    market_date: date,
    output_dir: Path,
    *,
    cutoff: datetime,
    codex_bin: str = "codex",
) -> Path:
    """Run live Codex search and write an immutable, review-required draft outside Git."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise WebResearchError("cutoff must be timezone-aware")
    output_path = output_dir.resolve()
    if output_path == PROJECT_ROOT or PROJECT_ROOT in output_path.parents:
        raise WebResearchError("research output must be outside the repository")
    output_path.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".web-research-", dir=output_path) as work_directory:
        work_path = Path(work_directory)
        schema_path = work_path / "schema.json"
        raw_path = work_path / "codex-output.json"
        schema_path.write_text(json.dumps(_output_schema()), encoding="utf-8")
        command = [
            codex_bin,
            "--search",
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--model",
            MODEL,
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(raw_path),
            _prompt(market_date, cutoff),
        ]
        try:
            # The argv shape is fixed, shell=False, and the CLI runs in a private scratch dir.
            result = subprocess.run(  # noqa: S603
                command,
                cwd=work_path,
                env=_minimal_codex_env(),
                capture_output=True,
                text=True,
                timeout=CODEX_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError as exc:
            raise WebResearchError("Codex CLI not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise WebResearchError("Codex search timed out") from exc
        if result.returncode != 0:
            raise WebResearchError(f"Codex search failed with exit code {result.returncode}")
        try:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WebResearchError("Codex returned invalid JSON") from exc
    accepted, rejected = validate_candidates(payload, market_date=market_date, cutoff=cutoff)
    if rejected == ["invalid_payload"]:
        raise WebResearchError("Codex returned invalid candidate container")
    run_id = uuid4().hex
    artifact_path = output_path / f"web-research-{market_date.isoformat()}-{run_id}.json"
    generated_at = datetime.now(UTC).isoformat()
    artifact = {
        "schema_version": "1.0",
        "market_date": market_date.isoformat(),
        "cutoff": cutoff.isoformat(),
        "generated_at": generated_at,
        "run_id": run_id,
        "provider": "codex",
        "model": MODEL,
        "review_status": "needs_review",
        "accepted_count": len(accepted),
        "rejected": rejected,
        "candidates": accepted,
    }
    receipt = {
        "schema_version": "1.0",
        "artifact": artifact_path.name,
        "cutoff": cutoff.isoformat(),
        "generated_at": generated_at,
        "model": MODEL,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected": rejected,
        "review_status": "needs_review",
    }
    _write_unique_json(artifact_path, artifact)
    _write_unique_json(output_path / "receipts" / artifact_path.name, receipt)
    return artifact_path
