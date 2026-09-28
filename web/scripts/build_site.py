"""Build a GitHub Pages artifact from the current five-session public snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from .audit_chart_artifact import audit_chart_artifact
    from .chart_contract import validate_public_chart
    from .generate_daily_summary import current_summaries
    from .generate_insights import SCHEMA as INSIGHT_SCHEMA
    from .generate_insights import _valid_history
    from .import_market_daily_report import _markdown as render_market_daily_markdown
    from .insight_contract import evaluate_watchpoints
    from .pipeline_health import health_report
    from .public_paths import public_snapshot_root, safe_public_report_path
except ImportError:
    from audit_chart_artifact import audit_chart_artifact
    from chart_contract import validate_public_chart
    from generate_daily_summary import current_summaries
    from generate_insights import SCHEMA as INSIGHT_SCHEMA
    from generate_insights import _valid_history
    from import_market_daily_report import _markdown as render_market_daily_markdown
    from insight_contract import evaluate_watchpoints
    from pipeline_health import health_report
    from public_paths import public_snapshot_root, safe_public_report_path


REPORT_SCHEMA = "market_intel_pages.reports.v1"
SUMMARY_SCHEMA = "market_intel_pages.daily_summaries.v1"
LEGACY_CONTINUOUS_REPORT_HASHES = {
    "2fd2991a411a709f40328a0fcdc0f1f382367276ca6ff07bc435bd4a46288c5c",
    "fc12070998d95440d9933b540b181d0b3f8f9c56d4e4b0397df341e542bcd4f7",
    "43adcc92a27dd7e8bea7de4b7299bc3b450fb1c84e0f1e63776d6b699786a3aa",
    "5a2a8ff17e0d51bcd8ce26f512444dfa6b9b9ea6d827577f467c4c36d4cd674b",
    "f75dfc294d87366de8357c2d203c16b7581ecf540b969f045058ab1d1980484a",
}
PUBLIC_SESSION_COUNT = 5
LEGACY_FILES = (
    "index.html",
    "app.js",
    "summary-utils.js",
    "report-markdown.js",
    "theme-utils.js",
    "styles.css",
)


def copy_public_charts(root: Path, output: Path, report_ids: set[str]) -> list[str]:
    """Copy only indexed and fully validated public chart manifests."""
    source_dir = (public_snapshot_root(root) / "data/charts").resolve()
    copied: list[str] = []
    for report_id in sorted(report_ids):
        source = public_snapshot_root(root) / "data/charts" / f"{report_id}.json"
        if not source.exists():
            continue
        if not source.resolve().is_relative_to(source_dir) or not source.is_file():
            raise ValueError(f"unsafe chart source: {report_id}")
        payload = validate_public_chart(json.loads(source.read_text(encoding="utf-8")), expected_id=report_id)
        destination = output / "data/charts" / f"{report_id}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        copied.append(report_id)
    return copied


def _overlay_astro_pages(root: Path, output: Path, report_ids: set[str]) -> None:
    """Build Astro against the already validated public snapshot."""
    if not (root / "package.json").is_file():
        return  # Synthetic Python-only build fixtures do not carry the site project.
    # Astro renames compiled assets, so its temporary output must share the
    # checkout filesystem; the reviewed data can still live on another mount.
    with tempfile.TemporaryDirectory(prefix="market-intel-astro-", dir=root.parent) as temporary:
        built = Path(temporary) / "site"
        env = {**os.environ, "ASTRO_DATA_ROOT": str(output), "ASTRO_OUT_DIR": str(built)}
        try:
            subprocess.run(
                ["npm", "run", "build"],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Astro static build failed") from exc
        if not (built / "index.html").is_file():
            raise ValueError("Astro index is missing")
        for report_id in report_ids:
            source = built / "reports" / report_id / "index.html"
            if not source.is_file():
                raise ValueError(f"Astro report page missing: {report_id}")
            destination = output / "reports" / report_id / "index.html"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        if (built / "_astro").is_dir():
            shutil.copytree(built / "_astro", output / "_astro", dirs_exist_ok=True)
        shutil.copy2(built / "index.html", output / "index.html")


def _read_index(path: Path, schema: str, key: str) -> tuple[dict, list[dict]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read index: {path}") from exc
    if payload.get("schema_version") != schema or not isinstance(payload.get(key), list):
        raise ValueError(f"unsupported {key} index")
    return payload, payload[key]


def _validate(reports: list[dict], summaries: list[dict]) -> None:
    by_id = {report.get("id"): report for report in reports}
    for summary in summaries:
        morning = by_id.get(summary.get("morning_report_id"))
        evening = by_id.get(summary.get("evening_report_id"))
        if not morning or not evening:
            raise ValueError("summary source report is missing")
        if morning.get("kind") != "morning" or evening.get("kind") != "evening":
            raise ValueError("summary source report kind is invalid")
        if summary.get("date") != morning.get("date"):
            raise ValueError("summary date must match its morning report")

    sessions = {report.get("date") for report in reports}
    if len(sessions) > PUBLIC_SESSION_COUNT:
        raise ValueError("public report snapshot exceeds five trading dates")


def _validate_daily_history(history: object, daily_report: Path) -> list[dict]:
    if not isinstance(history, dict):
        raise ValueError("invalid US daily history index")
    rows = history.get("reports")
    if history.get("schema_version") != "market_intel_pages.us_daily_history.v1":
        raise ValueError("invalid US daily history index")
    if not isinstance(rows, list) or not 1 <= len(rows) <= PUBLIC_SESSION_COUNT:
        raise ValueError("invalid US daily history index")

    dates = [str(row.get("run_id", "")).removeprefix("daily-") for row in rows]
    if dates != sorted(set(dates), reverse=True):
        raise ValueError("invalid US daily history dates")
    if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) for day in dates):
        raise ValueError("invalid US daily history dates")
    if not daily_report.is_file():
        raise ValueError("latest US daily report does not match history")
    latest = json.loads(daily_report.read_text(encoding="utf-8"))
    if latest != rows[0]:
        raise ValueError("latest US daily report does not match history")
    return rows


def _copy_daily_report_formats(root: Path, output: Path, payload: dict) -> None:
    run_id = payload.get("run_id", "")
    if not isinstance(run_id, str) or not re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", run_id):
        raise ValueError("invalid market daily report run_id")
    report_date = run_id.removeprefix("daily-")
    declared_formats = payload.get("report_formats", [])
    for suffix in ("md", "txt"):
        filename = f"reports/{report_date}-market-daily.{suffix}"
        source = public_snapshot_root(root) / filename
        if suffix in declared_formats and not source.is_file():
            raise ValueError(f"claimed market daily format missing: {filename}")
        if source.is_file():
            shutil.copy2(source, output / filename)
    if payload.get("publication") == "public":
        reading = output / f"reports/{report_date}-market-daily-no-citations.md"
        # Only exact already-published editions predate the dated-contract rule.
        projection_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        reading.write_text(
            render_market_daily_markdown(
                payload,
                include_references=False,
                allow_legacy_commodity=projection_hash in LEGACY_CONTINUOUS_REPORT_HASHES,
            ),
            encoding="utf-8",
        )


def _copy_daily_report(root: Path, output: Path) -> None:
    daily_report = public_snapshot_root(root) / "data/market_daily_report.json"
    history_path = public_snapshot_root(root) / "data/market_daily_reports.json"
    if history_path.is_file():
        history = json.loads(history_path.read_text(encoding="utf-8"))
        rows = _validate_daily_history(history, daily_report)
        shutil.copy2(history_path, output / "data/market_daily_reports.json")
    elif daily_report.is_file():
        rows = [json.loads(daily_report.read_text(encoding="utf-8"))]
    else:
        rows = []

    if daily_report.is_file():
        shutil.copy2(daily_report, output / "data/market_daily_report.json")
    for payload in rows:
        _copy_daily_report_formats(root, output, payload)


def _build_site_contents(root: Path, output: Path, summaries_path: Path | None = None) -> None:
    root = root.resolve()
    output = output.resolve()
    public_root = public_snapshot_root(root)
    summaries_path = (summaries_path or public_root / "data/daily_summaries.json").resolve()
    report_data, reports = _read_index(public_root / "data/reports.json", REPORT_SCHEMA, "reports")
    summary_data, summaries = _read_index(summaries_path, SUMMARY_SCHEMA, "summaries")
    _validate(reports, summaries)

    if output == root or output.is_relative_to(root):
        raise ValueError("build output must be outside the repository")
    if root.is_relative_to(output) or output == output.parent:
        raise ValueError("build output must not contain the repository")
    (output / "data").mkdir(parents=True)
    (output / "reports").mkdir()
    legacy = output / "legacy"
    legacy.mkdir()
    for filename in LEGACY_FILES:
        shutil.copy2(root / "src/legacy" / filename, legacy / filename)
    shutil.copy2(root / "src/lib/market-daily-utils.js", legacy / "market-daily-utils.js")
    shutil.copy2(public_root / "data/reports.json", output / "data/reports.json")
    copy_public_charts(root, output, {str(report["id"]) for report in reports})
    _copy_daily_report(root, output)
    summary_data["summaries"] = current_summaries(reports, summaries)
    (output / "data/daily_summaries.json").write_text(
        json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    health = health_report(report_data)
    (output / "data/health.json").write_text(
        json.dumps(health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    insight_path = public_root / "data/insights.json"
    insights = {
        "schema_version": INSIGHT_SCHEMA,
        "generation": {"status": "not_configured"},
        "insights": [],
        "outcomes": [],
    }
    if insight_path.exists():
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
        destination = output / source_url
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    _overlay_astro_pages(root, output, {str(report["id"]) for report in reports})


def build_site(root: Path, output: Path, summaries_path: Path | None = None) -> None:
    """Publish an entirely validated artifact, preserving the old one on failure."""
    root = root.resolve()
    output = output.resolve()
    if output == root or output.is_relative_to(root):
        raise ValueError("build output must be outside the repository")
    if root.is_relative_to(output) or output == output.parent:
        raise ValueError("build output must not contain the repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="market-intel-site-", dir=output.parent) as temporary:
        staging_root = Path(temporary)
        staged = staging_root / "new"
        previous = staging_root / "previous"
        _build_site_contents(root, staged, summaries_path)
        if output.exists():
            output.replace(previous)
        try:
            staged.replace(output)
        except OSError:
            if previous.exists():
                previous.replace(output)
            raise


def refresh_astro(root: Path, output: Path) -> None:
    """Render HTML again after the deploy workflow updates its reviewed snapshot."""
    root = root.resolve()
    output = output.resolve()
    if output == root or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("Astro snapshot must be outside the repository")
    _, reports = _read_index(output / "data/reports.json", REPORT_SCHEMA, "reports")
    _validate(reports, _read_index(output / "data/daily_summaries.json", SUMMARY_SCHEMA, "summaries")[1])
    audit_chart_artifact(output)
    _overlay_astro_pages(root, output, {str(report["id"]) for report in reports})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--output", type=Path, required=True, help="Pages artifact output directory")
    parser.add_argument("--summaries", type=Path, help="summary index override")
    parser.add_argument(
        "--refresh-astro", action="store_true", help="re-render HTML after commentary generation"
    )
    args = parser.parse_args()
    if args.refresh_astro:
        refresh_astro(args.root, args.output)
    else:
        build_site(args.root, args.output, args.summaries)
    print(f"Built public site at {args.output}")


if __name__ == "__main__":
    main()
