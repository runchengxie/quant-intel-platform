"""Stage a sourced Treasury-only refresh with parent evidence and a private receipt."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from market_intel_publication.us_daily_contract import _public_manifest, _read

from .macro import _rate_facts, rates_status
from .news_revision import _validate_paths
from .serialization import content_digest, dumps_json


def refresh_treasury_reference(
    source: Path, manifest: Path, output: Path, *, refreshed_at: datetime | None = None
) -> Path:
    """Create a validated candidate; the caller owns promotion and publication."""
    _validate_paths((source, manifest), output)
    original_bytes = source.read_bytes()
    original = _read(source)
    _public_manifest(source, manifest)
    if json.loads(original_bytes) != original:
        raise ValueError("Treasury refresh input changed during validation")
    if original.get("quality_summary", {}).get("revision") == "news_only":
        raise ValueError("news-only report requires an explicit market revision")
    day = date.fromisoformat(original["run_id"].removeprefix("daily-"))
    facts, _ = _rate_facts(datetime.fromisoformat(original["as_of"]))
    status = rates_status(facts, day)
    if (
        status["observation_date"] != status["expected_observation_date"]
        or status["quality"] == "degraded"
    ):
        raise ValueError("expected Treasury observations unavailable")
    revised_at = refreshed_at or datetime.now(UTC)
    if revised_at.tzinfo is None or any(fact.source_time > revised_at for fact in facts):
        raise ValueError("Treasury refresh evidence after revision cutoff")
    result = copy.deepcopy(original)
    updated = [json.loads(dumps_json(fact.to_dict())) for fact in facts]
    by_id = {fact["id"]: fact for fact in updated}
    existing = {fact["id"] for fact in result["facts"]}
    result["facts"] = [by_id.get(fact["id"], fact) for fact in result["facts"]]
    result["facts"].extend(fact for fact in updated if fact["id"] not in existing)
    result["source_status"]["rates"] = status
    result["missing_sources"] = [name for name in result["missing_sources"] if name != "rates_lag"]
    result["quality_summary"]["status"] = "degraded" if result["missing_sources"] else "ok"
    result["as_of"] = max(datetime.fromisoformat(original["as_of"]), revised_at).isoformat()
    result["generated_at"] = revised_at.isoformat()
    result["content_hash"] = content_digest(result)
    serialized = dumps_json(result)
    publication = {
        "schema_version": "1.0",
        "publication": "public",
        "report_file": "daily_report.json",
        "run_id": result["run_id"],
        "content_hash": result["content_hash"],
        "report_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
    }
    receipt = {
        "schema_version": "market_intel.treasury_refresh.v1",
        "run_id": result["run_id"],
        "parent_report_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "parent_content_hash": original["content_hash"],
        "original_as_of": original["as_of"],
        "result_content_hash": result["content_hash"],
        "refreshed_at": revised_at.isoformat(),
        "expected_observation_date": status["expected_observation_date"],
    }
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, value in (
        ("daily_report.json", serialized),
        ("publication.json", dumps_json(publication)),
        ("treasury_refresh_parent.json", original_bytes.decode()),
        ("treasury_refresh_receipt.json", dumps_json(receipt)),
    ):
        path = output / name
        with path.open("x", encoding="utf-8") as stream:
            stream.write(value)
        path.chmod(0o600)
    _read(output / "daily_report.json")
    _public_manifest(output / "daily_report.json", output / "publication.json")
    return output / "daily_report.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(refresh_treasury_reference(args.input, args.manifest, args.output))


if __name__ == "__main__":
    main()
