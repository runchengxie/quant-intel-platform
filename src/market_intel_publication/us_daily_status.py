"""Explicit status projection bound to published US report identities."""

from __future__ import annotations

import math
from datetime import date

SCHEMA = "market_intel_pages.us_daily_status.v1"
REQUIRED_MARKET_FACTS = frozenset(
    [f"index.{key}.change_percent" for key in ("spx", "dow", "nasdaq", "russell2000")]
    + [
        f"equity.{key}.{suffix}"
        for key in ("msft", "aapl", "nvda", "amzn", "googl", "meta")
        for suffix in ("close", "change_percent")
    ]
    + [
        f"cross_asset.{key}.{suffix}"
        for key in ("brent", "gold", "silver", "bitcoin_spot")
        for suffix in ("close", "change_percent")
    ]
    + [
        f"treasury.{key}.{suffix}"
        for key in ("2y", "5y", "10y", "30y")
        for suffix in ("level_percent", "change_bp")
    ]
)


def _research_status(report: dict) -> str:
    evidence_ids = {row.get("id") for row in report.get("facts", []) + report.get("events", [])}
    research = report.get("source_status", {}).get("research", {})
    if research.get("quality") == "reviewed" and any(
        claim.get("status") == "accepted"
        and claim.get("evidence_ids")
        and set(claim["evidence_ids"]) <= evidence_ids
        and claim.get("sources")
        and all(str(url).startswith("https://") for url in claim["sources"])
        for claim in report.get("claims", [])
    ):
        return "reviewed"
    if research.get("reason") == "not_connected" or not report.get("claims"):
        return "not_included"
    return "unknown"


def report_status(report: dict) -> dict:
    """Describe a public projection without mutating its signed source payload."""
    run_id = report["run_id"]
    day = run_id.removeprefix("daily-")
    date.fromisoformat(day)
    if report.get("publication") != "public":
        raise ValueError("US report status requires a published public report")
    content_hash = report.get("content_hash")
    if (
        not isinstance(content_hash, str)
        or len(content_hash) != 64
        or any(char not in "0123456789abcdef" for char in content_hash)
    ):
        raise ValueError("US report status requires a valid content hash")
    available = {
        row["id"]
        for row in report.get("facts", [])
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and row.get("observation_date") == day
        and row.get("quality") in {"ok", "reviewed"}
        and isinstance(row.get("value"), (int, float))
        and not isinstance(row["value"], bool)
        and math.isfinite(row["value"])
    }
    missing = sorted(REQUIRED_MARKET_FACTS - available)
    return {
        "run_id": run_id,
        "date": day,
        "content_hash": content_hash,
        "report_status": {
            "market": "incomplete" if missing else "complete",
            "research": _research_status(report),
            "publication": "published",
        },
        "missing_market_facts": missing,
    }


def status_index(reports: list[dict]) -> dict:
    """Build the allowlisted sidecar from the same exported public records."""
    return {"schema_version": SCHEMA, "reports": [report_status(row) for row in reports]}
