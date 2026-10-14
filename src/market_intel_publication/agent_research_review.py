"""Compare two verified public U.S. daily-report snapshots without inference."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent_market_brief import read_market_brief

BASIS_FIELDS = ("metric", "instrument", "unit", "source", "source_url")
IDENTITY_FIELDS = (
    "report_date",
    "as_of",
    "generated_at",
    "source",
    "artifact_hash",
    "content_hash",
)


@dataclass(frozen=True)
class ReportInput:
    source: Path
    manifest: Path
    date: str
    parent: Path | None = None


def _comparison_kind(baseline: dict, current: dict) -> str:
    if baseline["report_date"] > current["report_date"] or datetime.fromisoformat(
        baseline["as_of"]
    ) > datetime.fromisoformat(current["as_of"]):
        raise ValueError("report order must follow market dates and cutoffs")
    if baseline["artifact_hash"] == current["artifact_hash"]:
        return "identical_snapshot"
    if baseline["report_date"] != current["report_date"]:
        return "report_dates"
    if datetime.fromisoformat(baseline["generated_at"]) >= datetime.fromisoformat(
        current["generated_at"]
    ):
        raise ValueError("same-day revision order requires increasing generation time")
    return "revision"


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _fact_change(identifier: str, before: dict | None, after: dict | None) -> dict:
    row = {
        "id": identifier,
        "before_value": before.get("value") if before else None,
        "after_value": after.get("value") if after else None,
        "delta": None,
        "delta_unit": None,
        "basis_changes": [],
    }
    if before is None or after is None:
        return row | {"status": "added" if before is None else "removed"}
    changed = [field for field in BASIS_FIELDS if before.get(field) != after.get(field)]
    if changed or not (_number(before.get("value")) and _number(after.get("value"))):
        return row | {"status": "not_comparable", "basis_changes": changed}
    delta = after["value"] - before["value"]
    if not math.isfinite(delta):
        raise ValueError("fact delta must be finite")
    return row | {
        "status": "unchanged" if delta == 0 else "changed",
        "delta": delta,
        "delta_unit": "percentage_points" if after.get("unit") == "percent" else after.get("unit"),
    }


def _fact_changes(baseline: dict, current: dict) -> list[dict]:
    before = {fact["id"]: fact for fact in baseline["facts"]}
    after = {fact["id"]: fact for fact in current["facts"]}
    return [
        _fact_change(key, before.get(key), after.get(key))
        for key in sorted(before.keys() | after.keys())
    ]


def _claim_key(claim: dict) -> str:
    normalized = claim | {
        "evidence_ids": sorted(claim["evidence_ids"]),
        "sources": sorted(claim["sources"]),
    }
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False)


def _claims_by_evidence(report: dict) -> dict[tuple[str, ...], list[dict]]:
    groups: dict[tuple[str, ...], list[dict]] = {}
    for claim in report["claims"]:
        key = tuple(sorted(set(claim["evidence_ids"])))
        groups.setdefault(key, []).append(claim)
    return {key: sorted(rows, key=_claim_key) for key, rows in groups.items()}


def _claim_changes(baseline: dict, current: dict) -> list[dict]:
    before, after = _claims_by_evidence(baseline), _claims_by_evidence(current)
    result = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key, []), after.get(key, [])
        if not old or not new:
            status = "added" if not old else "removed"
        else:
            status = (
                "unchanged"
                if [_claim_key(row) for row in old] == [_claim_key(row) for row in new]
                else "revised"
            )
        result.append({"evidence_ids": list(key), "status": status, "before": old, "after": new})
    return result


def _quality_changes(baseline: dict, current: dict) -> dict:
    before = set(baseline["missing_sources"])
    after = set(current["missing_sources"])
    return {
        "baseline": {
            "summary": baseline["quality_summary"],
            "source_status": baseline["source_status"],
            "missing_sources": sorted(before),
        },
        "current": {
            "summary": current["quality_summary"],
            "source_status": current["source_status"],
            "missing_sources": sorted(after),
        },
        "missing_sources_added": sorted(after - before),
        "missing_sources_resolved": sorted(before - after),
    }


def _evidence_for(report: dict) -> dict[str, dict]:
    rows = [*report["facts"], *report["events"]]
    evidence = {row["id"]: row for row in rows}
    if len(evidence) != len(rows):
        raise ValueError("fact and event evidence IDs must not collide")
    return evidence


def read_research_review(baseline: ReportInput, current: ReportInput) -> dict[str, Any]:
    """Validate both owner bundles and describe differences, not hypothesis success."""
    before = read_market_brief(
        baseline.source,
        baseline.manifest,
        expected_date=baseline.date,
        previous_report=baseline.parent,
    )
    after = read_market_brief(
        current.source,
        current.manifest,
        expected_date=current.date,
        previous_report=current.parent,
    )
    kind = _comparison_kind(before, after)
    old, new = before["report"], after["report"]
    return {
        "schema_version": "quant.research_review.v1",
        "report_kind": "us_daily",
        "comparison_kind": kind,
        "baseline": {key: before[key] for key in IDENTITY_FIELDS},
        "current": {key: after[key] for key in IDENTITY_FIELDS},
        "fact_changes": _fact_changes(old, new),
        "claim_changes": _claim_changes(old, new),
        "data_quality": _quality_changes(old, new),
        "evidence": {
            "baseline": _evidence_for(old),
            "current": _evidence_for(new),
        },
        "evidence_level": "descriptive",
        "validation": {
            "artifact_integrity": "verified",
            "claim_status": "report_statements_only",
            "watchpoint_outcomes": "not_provided",
            "predictive_performance": "not_provided",
        },
        "limitations": [
            "Deltas compare one metric; they are not cumulative returns or causal estimates.",
            "Changed source or basis prevents comparison; units are not converted.",
            "Claim changes describe report content, not hypothesis success.",
            "IDs are snapshot-scoped; matching IDs may describe different events.",
            "Missing evidence is unavailable, not zero or evidence of no change.",
            "Backfills and revisions do not establish point-in-time data availability.",
            "Asia watchpoints and backtest performance are outside this report contract.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for prefix in ("baseline", "current"):
        parser.add_argument(f"--{prefix}", type=Path, required=True)
        parser.add_argument(f"--{prefix}-manifest", type=Path, required=True)
        parser.add_argument(f"--{prefix}-date", required=True)
        parser.add_argument(
            f"--{prefix}-parent", type=Path, help="Immutable parent of a news-only revision"
        )
    args = parser.parse_args(argv)
    try:
        result = read_research_review(
            ReportInput(
                args.baseline, args.baseline_manifest, args.baseline_date, args.baseline_parent
            ),
            ReportInput(
                args.current, args.current_manifest, args.current_date, args.current_parent
            ),
        )
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"research review rejected: {exc}", file=sys.stderr)
        return 2
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
