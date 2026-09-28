"""Generate evidence-linked commentary; preserve revisions in a private archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

try:
    from .generate_daily_summary import CHINA_TZ, select_source_pair
    from .insight_contract import build_context, evaluate_watchpoints, source_hash, validate_analysis
    from .insight_provider import generate
except ImportError:
    from generate_daily_summary import CHINA_TZ, select_source_pair
    from insight_contract import build_context, evaluate_watchpoints, source_hash, validate_analysis
    from insight_provider import generate

SCHEMA = "market_intel_pages.insights.v1"
PROMPT_VERSION = "market-insight-v1"
DEFAULT_MODELS = {
    "codex": "codex-cli",
    "gemini": "gemini-3.8-flash",
    "minimax": "MiniMax-M2.7",
    "deepseek": "deepseek-chat",
}
VALIDATION_ERROR_CODES = {
    "invalid analysis schema": "analysis_schema_invalid",
    "invalid claim count": "analysis_claim_count_invalid",
    "invalid claim": "analysis_claim_invalid",
    "invalid watchpoint count": "analysis_watchpoint_count_invalid",
    "watch condition must use a cited baseline metric": "analysis_watchpoint_evidence_invalid",
    "number not supported by cited evidence": "analysis_number_unsupported",
    "commentary too long": "analysis_length_exceeded",
}


def validation_error_code(error: ValueError) -> str:
    """Return a fixed public code without exposing model output or server prose."""
    message = str(error)
    return VALIDATION_ERROR_CODES.get(message, "analysis_validation_failed")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def archive_once(archive: Path, category: str, record: dict) -> None:
    raw = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    path = archive / category / f"{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(raw)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != raw:
            raise ValueError("archive hash collision") from None


def _history(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA or not isinstance(payload.get("insights"), list):
        raise ValueError("invalid insight history")
    return payload["insights"]


def _valid_history(history: list[dict], reports: list[dict]) -> list[dict]:
    by_id = {r["id"]: r for r in reports}
    valid = []
    for record in history:
        try:
            original_hashes = record.get("source_hashes", {})
            selected = [r for r in reports if r["id"] in original_hashes] if original_hashes else reports
            context = build_context(
                selected, by_id[record["morning_report_id"]], by_id[record["evening_report_id"]]
            )
            changed = (
                any(source_hash([r]) != original_hashes[r["id"]] for r in selected)
                if original_hashes
                else record["source_hash"] != context["source_hash"]
            )
            if changed or record["as_of"] != context["as_of"] or record["date"] != context["date"]:
                continue
            validate_analysis(record["analysis"], context)
            # Reconstruct trusted evidence from current sources, not cached remote text.
            valid.append(
                {
                    **record,
                    "evidence": context["evidence"],
                    "metrics": context["metrics"],
                    "source_report_ids": context["source_report_ids"],
                    "quality_warnings": context["quality_warnings"],
                }
            )
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return valid


def archive_verification(archive: Path, reports: list[dict]) -> None:
    """Keep checking every saved opinion, including replaced and expired ones."""
    index_path = archive / "verification_sources.json"
    previous = (
        json.loads(index_path.read_text(encoding="utf-8")).get("reports", []) if index_path.exists() else []
    )
    merged = {row["id"]: row for row in previous}
    merged.update({row["id"]: row for row in reports})
    archive_once(archive, "report_snapshots", {"reports": reports})
    write_json(
        index_path, {"schema_version": "market_intel_pages.reports.v1", "reports": list(merged.values())}
    )
    originals = {}
    for path in (archive / "insights").glob("*.json"):
        note = json.loads(path.read_text(encoding="utf-8"))
        try:
            validate_analysis(note["analysis"], note)
            if note["id"] not in originals or len(note["evidence"]) > len(originals[note["id"]]["evidence"]):
                originals[note["id"]] = note
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    for outcome in evaluate_watchpoints(list(originals.values()), list(merged.values())):
        if outcome["status"] != "pending":
            archive_once(archive, "outcomes", outcome)


def _load_history(path: Path, history_url: str | None) -> tuple[list[dict], str | None]:
    history = _history(path)
    history_warning = None
    if history_url:
        if not history_url.startswith("https://"):
            raise ValueError("history URL must use HTTPS")
        try:
            with urlopen(history_url, timeout=10) as response:
                published = json.loads(response.read(2_000_000))
            if published.get("schema_version") == SCHEMA and isinstance(published.get("insights"), list):
                history.extend(published["insights"])
        except (OSError, ValueError, AttributeError):
            history_warning = "published_history_unavailable"
    return history, history_warning


def _generate_with_fallback(generator, context, prompt, provider, model, api_keys):
    last_error = None
    for api_key in api_keys:
        try:
            return validate_analysis(generator(context, prompt, provider, model, api_key), context)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError("no API keys configured")


def _update_history(
    reports: list[dict],
    pair: tuple[dict, dict],
    history: list[dict],
    generation: dict,
    *,
    api_key,
    force: bool,
    generator,
    archive_dir,
) -> list[dict]:
    provider, model, now = generation["provider"], generation["model"], generation["checked_at"]
    morning, evening = pair
    context = build_context(reports, morning, evening)
    prompt = (Path(__file__).resolve().parent.parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(
        encoding="utf-8"
    )
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "source_hash": context["source_hash"],
                "prompt": prompt,
                "provider": provider,
                "model": model,
                "version": PROMPT_VERSION,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    generation["target_date"] = morning["date"]
    api_keys = [api_key] if isinstance(api_key, str) else [key for key in (api_key or []) if key]
    generation["analysis_attempts"] = len(api_keys)
    current = next(
        (
            row
            for row in history
            if row.get("morning_report_id") == morning["id"]
            and row.get("evening_report_id") == evening["id"]
            and row.get("source_hash") == context["source_hash"]
        ),
        None,
    )
    if (
        current
        and current.get("provider") == "codex"
        and (current.get("prompt_hash") != prompt_hash or current.get("prompt_version") != PROMPT_VERSION)
    ):
        current = None
    if (
        current
        and (current.get("provider") != provider or current.get("fingerprint") == fingerprint)
        and not force
    ):
        generation["status"] = "cached"
    elif not api_keys:
        generation["status"] = "not_configured"
    else:
        try:
            analysis = _generate_with_fallback(generator, context, prompt, provider, model, api_keys)
            identity = hashlib.sha256(
                json.dumps([fingerprint, analysis, now], sort_keys=True).encode()
            ).hexdigest()[:24]
            record = {
                **context,
                "id": identity,
                "generated_at": now,
                "generation_mode": "retrospective"
                if any(row.get("generation_mode") == "backfill" for row in pair)
                or (datetime.fromisoformat(now) - datetime.fromisoformat(context["as_of"])).total_seconds()
                > 3 * 3600
                else "daily",
                "provider": provider,
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "prompt_hash": prompt_hash,
                "fingerprint": fingerprint,
                "analysis": analysis,
            }
            if archive_dir:
                archive_once(archive_dir, "insights", record)
            history = [r for r in history if r["date"] != record["date"]] + [record]
            generation["status"] = "generated"
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            generation.update(status="unavailable", error_type=type(exc).__name__)
            if isinstance(exc, HTTPError):
                generation["diagnostics"] = getattr(exc, "diagnostics", {"http_status": exc.code})
            elif isinstance(exc, ValueError):
                generation["error_code"] = validation_error_code(exc)
    return history


def _latest_insights(history: list[dict], reports: list[dict]) -> list[dict]:
    dates = sorted({r["date"] for r in reports}, reverse=True)[:5]
    latest = {}
    prompt = (Path(__file__).resolve().parent.parent / "prompts" / f"{PROMPT_VERSION}.md").read_bytes()
    current_prompt_hash = hashlib.sha256(prompt).hexdigest()
    for row in sorted(
        history,
        key=lambda r: (
            r.get("provider") == "codex" and r.get("prompt_hash") == current_prompt_hash,
            r["generated_at"],
            r["id"],
        ),
    ):
        if row["date"] in dates:
            latest[row["date"]] = row
    return sorted(latest.values(), key=lambda r: r["date"], reverse=True)


def run(
    reports_path: Path,
    output_path: Path,
    *,
    provider="gemini",
    model=None,
    api_key=None,
    history_path=None,
    archive_dir=None,
    force=False,
    generator=generate,
    history_url=None,
) -> dict:
    if provider not in DEFAULT_MODELS:
        raise ValueError("unsupported provider")
    model = model or DEFAULT_MODELS[provider]
    data = json.loads(reports_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "market_intel_pages.reports.v1" or not isinstance(
        data.get("reports"), list
    ):
        raise ValueError("invalid report index")
    reports = data["reports"]
    if archive_dir:
        archive_dir = Path(archive_dir).resolve()
        if archive_dir.is_relative_to(Path(__file__).resolve().parent.parent):
            raise ValueError("archive must be outside the public repository")
    history, history_warning = _load_history(history_path or output_path, history_url)
    if archive_dir:
        for record in history:
            archive_once(archive_dir, "insights", record)
    history = _valid_history(history, reports)
    history = list({r["id"]: r for r in history}.values())
    pair = select_source_pair(reports)
    now = datetime.now(CHINA_TZ).isoformat(timespec="seconds")
    generation = {"status": "no_source_pair", "provider": provider, "model": model, "checked_at": now}
    if history_warning:
        generation["history_warning"] = history_warning
    if pair:
        history = _update_history(
            reports,
            pair,
            history,
            generation,
            api_key=api_key,
            force=force,
            generator=generator,
            archive_dir=archive_dir,
        )
    insights = _latest_insights(history, reports)
    outcomes = evaluate_watchpoints(insights, reports)
    if archive_dir:
        archive_verification(archive_dir, reports)
    result = {"schema_version": SCHEMA, "generation": generation, "insights": insights, "outcomes": outcomes}
    write_json(output_path, result)
    return result


def _environment_api_keys(prefix: str) -> list[str]:
    names = (
        (f"{prefix}_API_KEY", f"{prefix}_API_KEY_2", f"{prefix}_API_KEY_3")
        if prefix == "GEMINI"
        else (f"{prefix}_API_KEY",)
    )
    return [value for name in names if (value := os.environ.get(name))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--history-url")
    parser.add_argument("--archive-dir", type=Path)
    parser.add_argument(
        "--provider",
        choices=tuple(DEFAULT_MODELS.keys() - {"codex"}),
        default=os.environ.get("INSIGHT_PROVIDER", "gemini"),
    )
    parser.add_argument("--model")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    prefix = args.provider.upper()
    result = run(
        args.reports,
        args.output,
        provider=args.provider,
        model=args.model or os.environ.get(f"{prefix}_MODEL"),
        api_key=_environment_api_keys(prefix),
        history_path=args.history,
        history_url=args.history_url,
        archive_dir=args.archive_dir,
        force=args.force,
    )
    print(json.dumps(result["generation"], ensure_ascii=False))


if __name__ == "__main__":
    main()
