"""Public eligibility boundary shared by the owner content packer and verifier.

Legacy source trees may retain unindexed history. Strict snapshots may contain
only indexed public files and derived sidecars; transport never grants eligibility.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from market_intel_commentary.generate_daily_summary import current_summaries
from market_intel_commentary.generate_insights import _valid_history
from market_intel_commentary.insight_contract import build_context, evaluate_watchpoints
from market_intel_publication import site_content_contract as contract
from market_intel_publication.asia_news_contract import validate_public_asia_news
from market_intel_publication.chart_contract import validate_public_chart
from market_intel_publication.export_site_snapshot import LEGACY_CONTINUOUS_REPORT_HASHES, _validate
from market_intel_publication.pipeline_health import health_report
from market_intel_publication.us_daily_contract import (
    _public_payload,
    _unique_evidence_ids,
    _valid_claims,
    _valid_sourced_fact_date,
    _validate_report_shapes,
    _validate_schema_evidence,
)
from market_intel_publication.us_daily_status import status_index
from market_intel_publication.weekly_recap_bundle import weekly_history


def fields(value: object, allowed: str, required: str = "") -> dict:
    if (
        not isinstance(value, dict)
        or set(value) - set(allowed.split())
        or not set(required.split()) <= set(value)
    ):
        raise ValueError("unknown or missing public fields")
    return value


def public_string(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("public text field must be a string")


def validate_public_asia_report(row: object) -> dict:
    """Check the retained owner report shape without inferring prose semantics."""
    report = fields(
        row,
        "id date kind title summary sections source_url generation_mode asia_news_sha256",
        "id date kind title summary sections source_url",
    )
    for name, value in report.items():
        if name != "sections":
            public_string(value)
    if not isinstance(report["sections"], list):
        raise ValueError("Asia sections must be a list")
    for section in report["sections"]:
        contract.exact(section, "title paragraphs")
        public_string(section["title"])
        paragraphs = section["paragraphs"]
        if not isinstance(paragraphs, list) or any(
            not isinstance(value, str) for value in paragraphs
        ):
            raise ValueError("Asia paragraphs must be a list of strings")
    return report


def scalar(value: object) -> None:
    if isinstance(value, (dict, list)):
        raise ValueError("nested object in public scalar field")


def flat(value: dict) -> None:
    for item in value.values():
        if isinstance(item, list):
            for child in item:
                scalar(child)
        else:
            scalar(item)


def _read(public: Path, name: str) -> dict:
    contract.safe_path(name)
    return contract.read_json(contract.source_file(public / name, public))


def _index(
    public: Path, name: str, key: str, schema: str, *, generated: bool = False
) -> tuple[dict, list]:
    payload = _read(public, name)
    fields(
        payload,
        f"schema_version {key}" + (" generated_at" if generated else ""),
        f"schema_version {key}",
    )
    if payload["schema_version"] != schema or not isinstance(payload[key], list):
        raise ValueError("unsupported public index")
    if "generated_at" in payload:
        public_string(payload["generated_at"])
    return payload, payload[key]


def _asia(public: Path, allowed: set[str]) -> list[dict]:
    _, reports = _index(
        public, "data/reports.json", "reports", "market_intel_pages.reports.v1", generated=True
    )
    identities = []
    for row in reports:
        validate_public_asia_report(row)
        if row["id"] != f"{row['date']}-{row['kind']}" or row["kind"] not in {"morning", "evening"}:
            raise ValueError("invalid Asia report identity")
        if row["source_url"] != f"reports/{row['id']}.md":
            raise ValueError("invalid Asia report path")
        identities.append(row["id"])
        markdown = contract.source_file(public / contract.safe_path(row["source_url"]), public)
        allowed.add(row["source_url"])
        news = f"data/asia_news/{row['id']}.json"
        if (public / news).exists():
            validate_public_asia_news(
                _read(public, news), report_id=row["id"], report_sha256=contract.digest(markdown)
            )
            if row.get("asia_news_sha256") != _read(public, news)["content_sha256"]:
                raise ValueError("indexed Asia news hash mismatch")
            allowed.add(news)
        elif row.get("asia_news_sha256"):
            raise ValueError("indexed Asia news missing")
        chart = f"data/charts/{row['id']}.json"
        if (public / chart).exists():
            validate_public_chart(_read(public, chart), expected_id=row["id"])
            allowed.add(chart)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate Asia report identity")
    return reports


def _us_nested(row: dict) -> None:
    for family in ("facts", "events", "claims", "sections"):
        for item in row[family]:
            flat(item)
    _us_quality(row["quality_summary"])
    for source in row["source_status"].values():
        for key, value in source.items():
            if key == "reviewed_movers":
                for mover in value:
                    flat(contract.exact(mover, "ticker evidence_id"))
            else:
                scalar(value)


def _us_quality(quality: dict) -> None:
    for key, value in quality.items():
        if key == "treasury_revision":
            flat(
                fields(
                    value,
                    "schema_version parent_content_hash original_as_of revised_at expected_observation_date",
                )
            )
        elif key == "news_revision":
            flat(value)
        elif key == "news_revision_history":
            for record in value:
                flat(record)
        else:
            scalar(value)


def validate_public_us_daily(row: dict) -> None:
    """Validate the existing projection without reinterpreting raw source hashes."""
    _validate_report_shapes(row)
    flat(
        {
            key: value
            for key, value in row.items()
            if key
            not in {"facts", "events", "claims", "sections", "quality_summary", "source_status"}
        }
    )
    if row.get("publication") != "public" or row.get("schema_version") not in {"1.0", "1.1"}:
        raise ValueError("explicit public daily projection required")
    contract.hex_digest(row.get("content_hash"))
    contract.hex_digest(row.get("source_report_sha256"))
    projected = _public_payload(row, {"report_sha256": row["source_report_sha256"]})
    if "report_formats" not in row:
        projected.pop("report_formats")
    if contract.canonical(projected) != contract.canonical(row):
        raise ValueError("unknown or nonpublic daily projection fields")
    _us_nested(row)
    _validate_schema_evidence(row)
    legacy = (
        contract.digest(json.dumps(row, ensure_ascii=False, sort_keys=True).encode())
        in LEGACY_CONTINUOUS_REPORT_HASHES
    )
    if (
        not _unique_evidence_ids(row)
        or not _valid_claims(row["claims"])
        or (not legacy and not _valid_sourced_fact_date(row))
    ):
        raise ValueError("invalid public daily evidence")


def _us(public: Path, allowed: set[str], *, strict: bool) -> None:
    latest = "data/market_daily_report.json"
    history = "data/market_daily_reports.json"
    rows = []
    if (public / history).exists():
        _, rows = _index(public, history, "reports", "market_intel_pages.us_daily_history.v1")
        if not 1 <= len(rows) <= 5 or _read(public, latest) != rows[0]:
            raise ValueError("invalid US latest/history binding")
        allowed.add(history)
    elif (public / latest).exists():
        rows = [_read(public, latest)]
    dates = []
    for row in rows:
        validate_public_us_daily(row)
        run = row["run_id"]
        if not isinstance(run, str) or not re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", run):
            raise ValueError("invalid daily report identity")
        day = run.removeprefix("daily-")
        dates.append(day)
        for suffix in ("md", "txt", "no-citations.md"):
            name = (
                f"reports/{day}-market-daily.{suffix}"
                if suffix != "no-citations.md"
                else f"reports/{day}-market-daily-no-citations.md"
            )
            if (public / name).exists():
                contract.source_file(public / name, public)
                allowed.add(name)
            elif suffix in row.get("report_formats", []):
                raise ValueError("declared daily report download missing")
    if dates != sorted(set(dates), reverse=True):
        raise ValueError("US history dates must be unique and ordered")
    if rows:
        allowed.add(latest)
    status = "data/us_daily_status.json"
    if strict and (public / status).exists():
        if _read(public, status) != status_index(rows):
            raise ValueError("US status sidecar mismatch")
        allowed.add(status)


def _bind_insight_aggregate(note: dict, reports: list[dict]) -> None:
    """Bind surviving commentary to the same selected context as the owner."""
    by_id = {row["id"]: row for row in reports}
    hashes = note.get("source_hashes", {})
    selected = [row for row in reports if row["id"] in hashes] if hashes else reports
    context = build_context(
        selected, by_id[note["morning_report_id"]], by_id[note["evening_report_id"]]
    )
    if note.get("source_hash") != context["source_hash"]:
        raise ValueError("insight aggregate source hash mismatch")


def _commentary(public: Path, reports: list[dict], allowed: set[str], *, strict: bool) -> None:
    _, summaries = _index(
        public, "data/daily_summaries.json", "summaries", "market_intel_pages.daily_summaries.v1"
    )
    for row in summaries:
        flat(
            fields(
                row,
                "date text morning_report_id evening_report_id generated_at model provider prompt_version fingerprint source_hash insight_source_hash",
            )
        )
    _validate(reports, summaries)
    if strict and current_summaries(reports, summaries) != summaries:
        raise ValueError("summary source binding mismatch")
    name = "data/insights.json"
    if not (public / name).exists():
        return
    payload = _read(public, name)
    contract.exact(payload, "schema_version generation insights outcomes")
    if payload["schema_version"] != "market_intel_pages.insights.v1":
        raise ValueError("unsupported insight index")
    generation = fields(
        payload["generation"],
        "status provider model checked_at history_warning target_date analysis_attempts error_type diagnostics error_code",
    )
    flat({key: value for key, value in generation.items() if key != "diagnostics"})
    if "diagnostics" in generation:
        flat(fields(generation["diagnostics"], "http_status api_status reason category"))
    for note in payload["insights"]:
        fields(
            note,
            "as_of date morning_report_id evening_report_id source_report_ids source_hashes source_hash evidence metrics quality_warnings id generated_at generation_mode provider model prompt_version prompt_hash fingerprint analysis",
        )
        flat(
            {
                key: value
                for key, value in note.items()
                if key not in {"source_hashes", "evidence", "metrics", "analysis"}
            }
        )
        hashes = note.get("source_hashes", {})
        if not isinstance(hashes, dict) or (
            strict and not set(hashes) <= {row["id"] for row in reports}
        ):
            raise ValueError("unknown insight source identity")
        for identity, value in hashes.items():
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-(morning|evening)", identity):
                raise ValueError("invalid insight source identity")
            contract.hex_digest(value)
    # Owner reconstruction binds all nested evidence/metrics and analysis shapes.
    surviving = _valid_history(payload["insights"], reports)
    admitted_ids = {note["id"] for note in surviving}
    candidates = (
        payload["insights"]
        if strict
        else [note for note in payload["insights"] if note["id"] in admitted_ids]
    )
    if surviving != candidates:
        raise ValueError("insight public evidence mismatch")
    for note in surviving:
        _bind_insight_aggregate(note, reports)
    if strict and evaluate_watchpoints(payload["insights"], reports) != payload["outcomes"]:
        raise ValueError("insight outcomes mismatch")
    allowed.add(name)


def _derived(public: Path, allowed: set[str]) -> None:
    name = "data/health.json"
    if (public / name).exists():
        payload = _read(public, name)
        expected = health_report(
            _read(public, "data/reports.json"), now=datetime.fromisoformat(payload["checked_at"])
        )
        if payload != expected:
            raise ValueError("health sidecar binding mismatch")
        allowed.add(name)


def _exact_members(public: Path, allowed: set[str]) -> None:
    actual = set()
    for path in public.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("unsupported snapshot filesystem member")
        if path.is_file():
            name = path.relative_to(public).as_posix()
            contract.safe_path(name)
            actual.add(name)
    if actual != allowed:
        raise ValueError("unindexed or missing public snapshot file")


def validate_public_snapshot(
    public: Path, *, strict: bool = True, created_at_utc: str | None = None
) -> tuple[str, ...]:
    """Validate indexed families; strict mode rejects every unindexed payload file."""
    try:
        allowed = {"data/reports.json", "data/daily_summaries.json"}
        if strict:
            allowed.update({"data/health.json", "data/us_daily_status.json", "data/insights.json"})
        reports = _asia(public, allowed)
        _us(public, allowed, strict=strict)
        _commentary(public, reports, allowed, strict=strict)
        if strict:
            _derived(public, allowed)
            if created_at_utc is not None and contract.utc_time(
                _read(public, "data/health.json")["checked_at"]
            ) != contract.utc_time(created_at_utc):
                raise ValueError("health clock differs from candidate creation time")
        for name in ("data/weekly_recap.json", "data/weekly_recaps.json"):
            if (public / name).exists():
                _read(public, name)
                allowed.add(name)
        for row in weekly_history(public):
            for name in (row["source_url"], row["image"]["source_url"]):
                contract.source_file(public / contract.safe_path(name), public)
                allowed.add(name)
        if strict:
            _exact_members(public, allowed)
        if (
            len(allowed) > contract.MAX_FILES
            or sum((public / name).stat().st_size for name in allowed) > contract.MAX_EXPANDED_BYTES
        ):
            raise ValueError("public snapshot size limit exceeded")
        return tuple(sorted(allowed))
    except (KeyError, TypeError, AttributeError, OSError) as exc:
        raise ValueError("malformed public snapshot") from exc
