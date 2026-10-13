"""Read a verified public daily report as a deterministic Agent research brief."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from market_intel_publication.us_daily_contract import (
    _date,
    _public_manifest,
    _public_payload,
    _read,
)
from market_intel_publication.us_news_contract import validate_news_revision


def read_market_brief(
    source: Path, manifest_path: Path, *, expected_date: str, previous_report: Path | None = None
) -> dict[str, Any]:
    """Fail closed on publication, schema, hashes and requested report identity."""
    if date.fromisoformat(expected_date).isoformat() != expected_date:
        raise ValueError("expected date must use YYYY-MM-DD")
    content = source.read_bytes()
    raw = _read(source, content=content)
    manifest = _public_manifest(source, manifest_path, report_bytes=content)
    for key in ("as_of", "generated_at"):
        if datetime.fromisoformat(raw[key]).utcoffset() is None:
            raise ValueError(f"{key} must include a timezone")
    if source.name != manifest["report_file"] or _date(raw) != expected_date:
        raise ValueError("report filename or date does not match requested identity")
    if raw.get("quality_summary", {}).get("revision") == "news_only":
        if previous_report is None:
            raise ValueError("news revision requires its immutable original artifact")
        parent_content = previous_report.read_bytes()
        validate_news_revision(
            _read(previous_report, content=parent_content),
            raw,
            original_sha256=hashlib.sha256(parent_content).hexdigest(),
        )
    public = _public_payload(raw, manifest)
    evidence_ids = {
        item["id"]
        for item in [*public["facts"], *public["events"]]
        if str(item.get("source_url", "")).startswith("https://")
    }
    if any(not set(claim["evidence_ids"]).issubset(evidence_ids) for claim in public["claims"]):
        raise ValueError("claim evidence is missing from the public projection")
    return {
        "schema_version": "quant.market_brief.v1",
        "report_date": expected_date,
        "as_of": public["as_of"],
        "generated_at": public["generated_at"],
        "source": {"report_file": source.name, "run_id": public["run_id"]},
        "artifact_hash": manifest["report_sha256"],
        "content_hash": public["content_hash"],
        "data_quality": public["quality_summary"],
        "evidence_level": "descriptive",
        "limitations": [
            "This is a dated report snapshot, not live market data.",
            "Missing evidence is unavailable, not evidence of no change.",
            "Claims are reviewed report statements, not validated return forecasts.",
            "Scores, counterarguments and watchpoint outcomes are not supplied by this contract.",
        ],
        "report": public,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-date", required=True, help="Report date (YYYY-MM-DD)")
    parser.add_argument("--previous-report", type=Path, help="Immutable parent of a news revision")
    args = parser.parse_args(argv)
    try:
        result = read_market_brief(
            args.input,
            args.manifest,
            expected_date=args.expected_date,
            previous_report=args.previous_report,
        )
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"market brief rejected: {exc}", file=sys.stderr)
        return 2
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
