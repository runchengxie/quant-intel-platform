"""Evaluate the live public report snapshots at monitor runtime."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

try:
    from .pipeline_health import health_report
    from .public_site_calendar import session_expectation
except ImportError:
    from pipeline_health import health_report
    from public_site_calendar import session_expectation


US_TZ = ZoneInfo("America/New_York")
RUN_ID = re.compile(r"daily-(\d{4}-\d{2}-\d{2})\Z")


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def _finding(key: str, status: str) -> dict[str, str]:
    label = "Asia evening report" if key == "asia" else "U.S. daily report"
    summaries = {
        "deferred": "Asia calendar defers the Asia evening freshness check until the next session deadline; existing alerts remain open.",
        "ok": f"{label} is within the configured freshness window.",
        "review": f"Review freshness of the {label}; a market closure may explain the age.",
        "unavailable": f"{label} snapshot is unavailable or has invalid metadata; review the public data.",
    }
    return {"key": key, "status": status, "summary": summaries[status]}


def _calendar_expectation(calendar, now, latest_date):
    if calendar is None:
        return None
    expectation = session_expectation(calendar, now)
    if not calendar["days"].get(latest_date, False):
        raise ValueError("report target is not an Asia session")
    return expectation


def _calendar_report_status(latest_date, generated, status, expectation, now, max_age_hours):
    expected, deferred, _deadline = expectation
    if generated is None or status in {"missing", "invalid_timestamp"}:
        return "unavailable"
    if latest_date < expected:
        return "review"
    if generated.astimezone(ZoneInfo("Asia/Shanghai")).date() < date.fromisoformat(latest_date):
        return "unavailable"
    if deferred and latest_date == expected and status == "stale":
        return "deferred"
    return "review" if (now - generated).total_seconds() > max_age_hours * 3600 else "ok"


def _asia_status(reports: dict, now: datetime, max_age_hours: int, calendar: dict | None) -> str:
    rows = reports.get("reports")
    if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
        return "unavailable"
    evenings = [row for row in rows if row.get("kind") == "evening"]
    if not evenings or any(not isinstance(row.get("date"), str) for row in evenings):
        return "unavailable"
    try:
        latest_date = max(row["date"] for row in evenings)
        latest = [row for row in evenings if row["date"] == latest_date]
        expectation = _calendar_expectation(calendar, now, latest_date)
        result = health_report({"reports": latest}, now=now, max_age_hours=max_age_hours)
        source_time = result["latest_source_generated_at"]
        generated = datetime.fromisoformat(source_time) if source_time else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return "unavailable"
    if generated is not None and generated > now:
        return "unavailable"
    if expectation is not None:
        return _calendar_report_status(
            latest_date, generated, result["status"], expectation, now, max_age_hours
        )
    if result["status"] == "stale":
        return "review"
    if result["status"] == "calendar_unverified":
        if generated is None:
            return "unavailable"
        if (now - generated).total_seconds() > max_age_hours * 3600:
            return "review"
        return "ok"
    return "unavailable"


def _us_status(us_report: dict, now: datetime, max_age_hours: int) -> str:
    run_id = us_report.get("run_id")
    generated_at = us_report.get("generated_at")
    if not isinstance(run_id, str) or not isinstance(generated_at, str):
        return "unavailable"
    match = RUN_ID.fullmatch(run_id)
    if match is None:
        return "unavailable"
    try:
        target = date.fromisoformat(match.group(1))
        generated = datetime.fromisoformat(generated_at)
    except ValueError:
        return "unavailable"
    if generated.tzinfo is None or generated.utcoffset() is None:
        return "unavailable"
    if generated > now or target > now.astimezone(US_TZ).date():
        return "unavailable"
    target_end = datetime.combine(target, time.max, tzinfo=US_TZ)
    generated_age = (now - generated).total_seconds() / 3600
    market_age = (now - target_end).total_seconds() / 3600
    return "review" if max(generated_age, market_age) > max_age_hours else "ok"


def evaluate_public_snapshots(
    reports: dict, us_report: dict, *, now: datetime, max_age_hours: int = 96, calendar: dict | None = None
) -> list[dict[str, str]]:
    """Return bounded, content-free findings for the two published report streams."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("check time must include timezone")
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    asia_status = (
        _asia_status(reports, now, max_age_hours, calendar) if isinstance(reports, dict) else "unavailable"
    )
    us_status = _us_status(us_report, now, max_age_hours) if isinstance(us_report, dict) else "unavailable"
    return [_finding("asia", asia_status), _finding("us", us_status)]


def fetch_public_snapshots(
    base_url: str, *, timeout_seconds: int = 10, max_bytes: int = 4_000_000
) -> tuple[dict, dict]:
    """Fetch the two fixed JSON paths; unreadable snapshots become empty dictionaries."""
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or ".." in parsed.path.split("/")
    ):
        raise ValueError("base_url must be an HTTPS Pages base URL")
    if timeout_seconds <= 0 or max_bytes <= 0:
        raise ValueError("timeout_seconds and max_bytes must be positive")
    base = base_url.rstrip("/")
    opener = build_opener(_NoRedirectHandler())
    snapshots = []
    for filename in ("reports.json", "market_daily_report.json"):
        request = Request(f"{base}/data/{filename}", headers={"Accept": "application/json"})
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                if response.geturl() != request.full_url:
                    snapshots.append({})
                    continue
                raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                snapshots.append({})
                continue
            payload = json.loads(raw)
            snapshots.append(payload if isinstance(payload, dict) else {})
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
            snapshots.append({})
    return snapshots[0], snapshots[1]
