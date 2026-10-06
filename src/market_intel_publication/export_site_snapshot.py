"""Export a validated public report snapshot for a static website consumer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from market_intel_commentary.generate_daily_summary import current_summaries
from market_intel_commentary.generate_insights import SCHEMA as INSIGHT_SCHEMA
from market_intel_commentary.generate_insights import _valid_history
from market_intel_commentary.insight_contract import evaluate_watchpoints
from market_intel_publication.asia_news_contract import public_asia_projection
from market_intel_publication.import_market_daily_report import _markdown as render_daily_report
from market_intel_publication.pipeline_health import health_report
from market_intel_publication.public_paths import public_snapshot_root, safe_public_report_path

REPORT_SCHEMA = "market_intel_pages.reports.v1"
SUMMARY_SCHEMA = "market_intel_pages.daily_summaries.v1"
PUBLIC_SESSION_COUNT = 5
LEGACY_CONTINUOUS_REPORT_HASHES = {
    "2fd2991a411a709f40328a0fcdc0f1f382367276ca6ff07bc435bd4a46288c5c",
    "fc12070998d95440d9933b540b181d0b3f8f9c56d4e4b0397df341e542bcd4f7",
    "43adcc92a27dd7e8bea7de4b7299bc3b450fb1c84e0f1e63776d6b699786a3aa",
    "5a2a8ff17e0d51bcd8ce26f512444dfa6b9b9ea6d827577f467c4c36d4cd674b",
    "f75dfc294d87366de8357c2d203c16b7581ecf540b969f045058ab1d1980484a",
}


def _read_index(path: Path, schema: str, key: str) -> tuple[dict, list[dict]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read index: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != schema:
        raise ValueError(f"unsupported {key} index")
    rows = payload.get(key)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"unsupported {key} index")
    return payload, rows


def _validate(reports: list[dict], summaries: list[dict]) -> None:
    by_id = {report.get("id"): report for report in reports}
    for summary in summaries:
        morning = by_id.get(summary.get("morning_report_id"))
        evening = by_id.get(summary.get("evening_report_id"))
        if not morning or not evening:
            raise ValueError("summary source report is missing")
        if morning.get("kind") not in {"morning", "evening"} or evening.get("kind") != "evening":
            raise ValueError("summary source report kind is invalid")
        current_date, baseline_date = morning.get("date"), evening.get("date")
        if not isinstance(current_date, str) or not isinstance(baseline_date, str):
            raise ValueError("summary source report date is invalid")
        if summary.get("date") != current_date:
            raise ValueError("summary date must match its current report")
        if baseline_date > current_date or (
            morning.get("kind") == "evening" and baseline_date == current_date
        ):
            raise ValueError("summary baseline must precede its current report")
    if len({report.get("date") for report in reports}) > PUBLIC_SESSION_COUNT:
        raise ValueError("public report snapshot exceeds five trading dates")


def _copy_checked_file(source: Path, destination: Path, root: Path) -> None:
    if (
        source.is_symlink()
        or not source.is_file()
        or not source.resolve().is_relative_to(root.resolve())
    ):
        raise ValueError(f"unsafe public source: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_charts(public_root: Path, output: Path, report_ids: set[str]) -> None:
    from market_intel_publication.chart_contract import validate_public_chart

    chart_dir = public_root / "data/charts"
    if not chart_dir.exists():
        return
    if chart_dir.is_symlink():
        raise ValueError("unsafe public chart directory")
    for path in chart_dir.iterdir():
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix != ".json"
            or path.stem not in report_ids
        ):
            raise ValueError(f"chart identity or file type is unsafe: {path.name}")
        payload = validate_public_chart(
            json.loads(path.read_text(encoding="utf-8")), expected_id=path.stem
        )
        target = output / "data/charts" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def _copy_news(public_root: Path, output: Path, reports: list[dict]) -> None:
    source_dir = public_root / "data/asia_news"
    if source_dir.is_symlink():
        raise ValueError("unsafe public news directory")
    for report in reports:
        path = source_dir / f"{report['id']}.json"
        if not path.exists():
            if report.get("asia_news_sha256"):
                raise ValueError("indexed Asia news missing")
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("unsafe public news source")
        markdown = public_root / report["source_url"]
        payload = public_asia_projection(
            json.loads(path.read_text(encoding="utf-8")),
            report_id=report["id"],
            report_sha256=hashlib.sha256(markdown.read_bytes()).hexdigest(),
        )
        if (
            report.get("asia_news_sha256")
            and report["asia_news_sha256"] != payload["content_sha256"]
        ):
            raise ValueError("indexed Asia news hash mismatch")
        target = output / "data/asia_news" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def _copy_us_daily(public_root: Path, output: Path) -> None:
    latest = public_root / "data/market_daily_report.json"
    history_path = public_root / "data/market_daily_reports.json"
    if history_path.is_file():
        history = json.loads(history_path.read_text(encoding="utf-8"))
        rows = (
            history.get("reports")
            if history.get("schema_version") == "market_intel_pages.us_daily_history.v1"
            else None
        )
        if not isinstance(rows, list) or not rows or len(rows) > PUBLIC_SESSION_COUNT:
            raise ValueError("invalid US daily history index")
        dates = [str(row.get("run_id", "")).removeprefix("daily-") for row in rows]
        if dates != sorted(set(dates), reverse=True) or not latest.is_file():
            raise ValueError("invalid US daily history dates")
        if json.loads(latest.read_text(encoding="utf-8")) != rows[0]:
            raise ValueError("latest US daily report does not match history")
        _copy_checked_file(history_path, output / "data/market_daily_reports.json", public_root)
    else:
        rows = [json.loads(latest.read_text(encoding="utf-8"))] if latest.is_file() else []
    if latest.is_file():
        _copy_checked_file(latest, output / "data/market_daily_report.json", public_root)
    for row in rows:
        run_id = row.get("run_id", "")
        if not isinstance(run_id, str) or not re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", run_id):
            raise ValueError("invalid market daily report run_id")
        day = run_id.removeprefix("daily-")
        for suffix in ("md", "txt"):
            path = public_root / f"reports/{day}-market-daily.{suffix}"
            declared_formats = row.get("report_formats", [])
            if suffix in declared_formats and not path.is_file():
                raise ValueError(f"claimed market daily format missing: reports/{path.name}")
            if path.exists():
                _copy_checked_file(path, output / f"reports/{path.name}", public_root)
        if row.get("publication") == "public":
            path = output / f"reports/{day}-market-daily-no-citations.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            projection_hash = hashlib.sha256(
                json.dumps(row, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            path.write_text(
                render_daily_report(
                    row,
                    include_references=False,
                    allow_legacy_commodity=projection_hash in LEGACY_CONTINUOUS_REPORT_HASHES,
                ),
                encoding="utf-8",
            )


def _build(root: Path, output: Path, summaries_path: Path | None) -> None:
    public_root = public_snapshot_root(root)
    report_data, reports = _read_index(public_root / "data/reports.json", REPORT_SCHEMA, "reports")
    summary_path = summaries_path or public_root / "data/daily_summaries.json"
    summary_data, summaries = _read_index(summary_path, SUMMARY_SCHEMA, "summaries")
    _validate(reports, summaries)
    (output / "data").mkdir(parents=True)
    (output / "reports").mkdir()
    shutil.copy2(public_root / "data/reports.json", output / "data/reports.json")
    _copy_charts(public_root, output, {str(report["id"]) for report in reports})
    _copy_us_daily(public_root, output)
    summary_data["summaries"] = current_summaries(reports, summaries)
    (output / "data/daily_summaries.json").write_text(
        json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "data/health.json").write_text(
        json.dumps(health_report(report_data), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    insight_path = public_root / "data/insights.json"
    insights = {
        "schema_version": INSIGHT_SCHEMA,
        "generation": {"status": "not_configured"},
        "insights": [],
        "outcomes": [],
    }
    if insight_path.is_file():
        candidate = json.loads(insight_path.read_text(encoding="utf-8"))
        if candidate.get("schema_version") != INSIGHT_SCHEMA:
            raise ValueError("unsupported insight index")
        insights = {**candidate, "insights": _valid_history(candidate.get("insights", []), reports)}
        insights["outcomes"] = evaluate_watchpoints(insights["insights"], reports)
    (output / "data/insights.json").write_text(
        json.dumps(insights, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for report in reports:
        source_url = report.get("source_url")
        if not isinstance(source_url, str):
            raise ValueError("report source_url must be a string")
        source = safe_public_report_path(root, source_url)
        if not source.is_file():
            raise ValueError(f"report Markdown is missing or unsafe: {source_url}")
        _copy_checked_file(source, output / source_url, public_root)
    _copy_news(public_root, output, reports)


def export_site_snapshot(root: Path, output: Path, summaries_path: Path | None = None) -> None:
    """Atomically export validated public data, leaving the previous snapshot intact on failure."""
    root, output = root.resolve(), output.resolve()
    if (
        output == root
        or output.is_relative_to(root)
        or root.is_relative_to(output)
        or output == output.parent
    ):
        raise ValueError("build output must be outside the repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="market-intel-snapshot-", dir=output.parent
    ) as temporary:
        staged = Path(temporary) / "new"
        _build(root, staged, summaries_path)
        previous = Path(temporary) / "previous"
        if output.exists():
            output.replace(previous)
        try:
            staged.replace(output)
        except OSError:
            if previous.exists():
                previous.replace(output)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summaries", type=Path)
    args = parser.parse_args()
    export_site_snapshot(args.root, args.output, args.summaries)
    print(f"Exported public report snapshot at {args.output}")


if __name__ == "__main__":
    main()
