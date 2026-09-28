"""Archive the complete report set locally and keep only five sessions public."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from .public_paths import public_snapshot_root, safe_public_report_path
except ImportError:
    from public_paths import public_snapshot_root, safe_public_report_path

REPORT_SCHEMA = "market_intel_pages.reports.v1"
SUMMARY_SCHEMA = "market_intel_pages.daily_summaries.v1"
PUBLIC_SESSION_COUNT = 5


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON file: {path}") from exc


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_index(payload: dict, schema: str, key: str) -> list[dict]:
    if payload.get("schema_version") != schema or not isinstance(payload.get(key), list):
        raise ValueError(f"unsupported {key} index")
    return payload[key]


def _safe_report_path(root: Path, source_url: str) -> Path:
    source = Path(source_url)
    if source.is_absolute() or not source.parts or source.parts[0] != "reports":
        raise ValueError(f"invalid report source path: {source_url}")
    resolved = (root / source).resolve()
    if not resolved.is_relative_to((root / "reports").resolve()):
        raise ValueError(f"invalid report source path: {source_url}")
    return resolved


def _merge_by_id(existing: list[dict], incoming: list[dict], key: str) -> list[dict]:
    merged = {record[key]: record for record in existing}
    for record in incoming:
        if key not in record:
            raise ValueError(f"record missing {key}")
        merged[record[key]] = record
    return sorted(merged.values(), key=lambda item: (item.get("date", ""), item.get(key, "")))


def _merge_summaries(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = {
        (record.get("morning_report_id"), record.get("evening_report_id")): record for record in existing
    }
    for record in incoming:
        pair = (record.get("morning_report_id"), record.get("evening_report_id"))
        if not all(pair):
            raise ValueError("summary is missing source report IDs")
        merged[pair] = record
    return sorted(merged.values(), key=lambda item: (item.get("date", ""), item.get("morning_report_id", "")))


def _archive_reports(root: Path, archive_dir: Path, reports: list[dict]) -> None:
    for report in reports:
        source_url = report.get("source_url")
        if not source_url:
            raise ValueError(f"report {report.get('id')} has no source_url")
        source = safe_public_report_path(root, source_url)
        if not source.is_file():
            raise ValueError(f"report Markdown is missing: {source_url}")
        destination = _safe_report_path(archive_dir, source_url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def sync_snapshot(root: Path, archive_dir: Path) -> None:
    root = root.resolve()
    archive_dir = archive_dir.resolve()
    if archive_dir == root or archive_dir.is_relative_to(root):
        raise ValueError("archive directory must be outside the repository")

    public_root = public_snapshot_root(root)
    report_index_path = public_root / "data/reports.json"
    summary_index_path = public_root / "data/daily_summaries.json"
    incoming_report_index = _read_json(report_index_path)
    incoming_summary_index = _read_json(summary_index_path)
    incoming_reports = _validate_index(incoming_report_index, REPORT_SCHEMA, "reports")
    incoming_summaries = _validate_index(incoming_summary_index, SUMMARY_SCHEMA, "summaries")

    _archive_reports(root, archive_dir, incoming_reports)

    archive_report_path = archive_dir / "data/reports.json"
    archive_summary_path = archive_dir / "data/daily_summaries.json"
    if archive_report_path.exists():
        archived_report_index = _read_json(archive_report_path)
        archived_reports = _validate_index(archived_report_index, REPORT_SCHEMA, "reports")
    else:
        archived_report_index = {"schema_version": REPORT_SCHEMA, "generated_at": "", "reports": []}
        archived_reports = []
    if archive_summary_path.exists():
        archived_summary_index = _read_json(archive_summary_path)
        archived_summaries = _validate_index(archived_summary_index, SUMMARY_SCHEMA, "summaries")
    else:
        archived_summary_index = {"schema_version": SUMMARY_SCHEMA, "summaries": []}
        archived_summaries = []

    all_reports = _merge_by_id(archived_reports, incoming_reports, "id")
    all_summaries = _merge_summaries(archived_summaries, incoming_summaries)

    all_report_ids = {report["id"] for report in all_reports}
    for summary in all_summaries:
        if (
            summary.get("morning_report_id") not in all_report_ids
            or summary.get("evening_report_id") not in all_report_ids
        ):
            raise ValueError("summary source report is missing from local archive")

    archive_report_index = {
        **archived_report_index,
        **incoming_report_index,
        "schema_version": REPORT_SCHEMA,
        "reports": all_reports,
    }
    archive_summary_index = {
        **archived_summary_index,
        **incoming_summary_index,
        "schema_version": SUMMARY_SCHEMA,
        "summaries": all_summaries,
    }
    _write_json(archive_report_path, archive_report_index)
    _write_json(archive_summary_path, archive_summary_index)

    # Verify the complete archive before changing the public working tree.
    for report in all_reports:
        archived_markdown = _safe_report_path(archive_dir, report["source_url"])
        if not archived_markdown.is_file():
            raise ValueError(f"archived report Markdown is missing: {report['source_url']}")

    _publish_snapshot(
        root, archive_dir, all_reports, all_summaries, incoming_report_index, incoming_summary_index
    )


def _publish_snapshot(
    root: Path,
    archive_dir: Path,
    all_reports: list[dict],
    all_summaries: list[dict],
    incoming_report_index: dict,
    incoming_summary_index: dict,
) -> None:
    public_root = public_snapshot_root(root)
    report_index_path = public_root / "data/reports.json"
    summary_index_path = public_root / "data/daily_summaries.json"
    session_dates = sorted(
        {report["date"] for report in all_reports},
        reverse=True,
    )[:PUBLIC_SESSION_COUNT]
    public_dates = set(session_dates)
    public_reports = [report for report in all_reports if report.get("date") in public_dates]
    public_ids = {report["id"] for report in public_reports}
    public_summaries = [
        summary
        for summary in all_summaries
        if summary.get("date") in public_dates
        and summary.get("morning_report_id") in public_ids
        and summary.get("evening_report_id") in public_ids
    ]

    for report in public_reports:
        source = _safe_report_path(archive_dir, report["source_url"])
        destination = safe_public_report_path(root, report["source_url"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    public_report_index = {
        **incoming_report_index,
        "schema_version": REPORT_SCHEMA,
        "reports": public_reports,
    }
    public_summary_index = {
        **incoming_summary_index,
        "schema_version": SUMMARY_SCHEMA,
        "summaries": public_summaries,
    }
    _write_json(report_index_path, public_report_index)
    _write_json(summary_index_path, public_summary_index)

    referenced = {report.get("source_url") for report in public_reports}
    reports_dir = public_root / "reports"
    if reports_dir.exists():
        for markdown in reports_dir.glob("*.md"):
            relative = markdown.relative_to(public_root).as_posix()
            if relative not in referenced:
                markdown.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--archive-dir", type=Path, required=True, help="full local archive outside the repository"
    )
    args = parser.parse_args()
    sync_snapshot(args.root, args.archive_dir)
    print("Archived all reports locally; public snapshot contains at most five trading dates.")


if __name__ == "__main__":
    main()
