"""Report source freshness without confusing a new build with new market data."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time
from pathlib import Path

try:
    from .generate_daily_summary import CHINA_TZ, report_generated_at, select_source_pair
except ImportError:
    from generate_daily_summary import CHINA_TZ, report_generated_at, select_source_pair


def _freshness_status(
    now: datetime,
    source_age: float | None,
    target: date | None,
    expected_date: str | None,
    max_age_hours: int,
) -> str:
    expected = date.fromisoformat(expected_date) if expected_date else None
    if source_age is None or target is None:
        return "missing"
    if source_age < 0 or target > now.astimezone(CHINA_TZ).date():
        return "invalid_timestamp"
    if expected:
        return "current" if target >= expected else "behind"
    # A freshly regenerated old report must not hide the age of its market date.
    target_end = datetime.combine(target, time.max, tzinfo=CHINA_TZ)
    target_age_hours = (now - target_end).total_seconds() / 3600
    if source_age > max_age_hours or target_age_hours > max_age_hours:
        return "stale"
    return "calendar_unverified"


def health_report(data: dict, *, now=None, expected_date=None, max_age_hours=72) -> dict:
    now = now or datetime.now(CHINA_TZ)
    if now.tzinfo is None:
        raise ValueError("health check time must include timezone")
    reports = data.get("reports", [])
    times = [generated for r in reports if (generated := report_generated_at(r)) is not None]
    latest = max(times) if times else None
    latest_date = max((r["date"] for r in reports), default=None)
    age = round((now - latest).total_seconds() / 3600, 1) if latest else None
    target = date.fromisoformat(latest_date) if latest_date else None
    target_age_days = (now.astimezone(CHINA_TZ).date() - target).days if target else None
    status = _freshness_status(now, age, target, expected_date, max_age_hours)
    pair = select_source_pair(reports)
    return {
        "schema_version": "market_intel_pages.health.v1",
        "checked_at": now.isoformat(),
        "status": status,
        "latest_target_date": latest_date,
        "latest_source_generated_at": latest.isoformat() if latest else None,
        "source_age_hours": age,
        "latest_target_age_days": target_age_days,
        "expected_date": expected_date,
        "max_age_hours": max_age_hours,
        "index_generated_at": data.get("generated_at"),
        "report_count": len(reports),
        "pair_available": pair is not None,
        "latest_pair_date": pair[0]["date"] if pair else None,
        "latest_date_kinds": sorted({r["kind"] for r in reports if r["date"] == latest_date}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--expected-date", help="Expected target from the upstream exchange calendar (YYYY-MM-DD)"
    )
    parser.add_argument("--max-age-hours", type=int, default=72)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = health_report(
        json.loads(args.reports.read_text(encoding="utf-8")),
        expected_date=args.expected_date,
        max_age_hours=args.max_age_hours,
    )
    raw = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
    print(raw)
    if args.strict and result["status"] in ("missing", "invalid_timestamp", "stale", "behind"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
