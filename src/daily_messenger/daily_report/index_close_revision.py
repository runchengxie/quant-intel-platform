"""Stage index close enrichment while retaining all original report evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from market_intel_publication.us_daily_contract import _public_manifest, _read

from .index_quotes import INDICES, fetch_index_facts
from .news_revision import _validate_paths
from .serialization import content_digest, dumps_json


def enrich_index_closes(source: Path, manifest: Path, output: Path) -> Path:
    """Validate, fetch and stage an additive market revision; never promote it."""
    _validate_paths((source, manifest), output)
    original_bytes = source.read_bytes()
    original = _read(source)
    _public_manifest(source, manifest)
    if json.loads(original_bytes) != original:
        raise ValueError("index enrichment input changed during validation")
    if original.get("quality_summary", {}).get("revision") == "news_only":
        raise ValueError("news-only report requires an explicit market revision contract")
    day = date.fromisoformat(original["run_id"].removeprefix("daily-"))
    by_id = {fact["id"]: fact for fact in original["facts"]}
    if any(f"index.{key}.close" in by_id for _, key, _ in INDICES):
        raise ValueError("report already includes index closes")
    facts, missing = fetch_index_facts(day)
    if missing:
        raise ValueError("same-day index close source unavailable")
    for fact in facts:
        if not fact.id.endswith(".change_percent"):
            continue
        previous = by_id.get(fact.id)
        if (
            not isinstance(fact.value, (int, float))
            or not previous
            or previous.get("observation_date") != day.isoformat()
            or abs(float(previous["value"]) - float(fact.value)) > 0.0051
        ):
            raise ValueError("fetched index return conflicts with retained report evidence")
    cutoff = datetime.fromisoformat(original["as_of"])
    if cutoff.tzinfo is None or any(
        fact.source_time.tzinfo is None or fact.source_time > cutoff
        for fact in facts
        if fact.id.endswith(".close")
    ):
        raise ValueError(
            "index close enrichment acquired after original evidence cutoff; not publish-ready"
        )
    result = copy.deepcopy(original)
    added = [json.loads(dumps_json(fact.to_dict())) for fact in facts if fact.id.endswith(".close")]
    result["facts"].extend(added)
    for section in result.get("sections", []):
        if section.get("key") == "market":
            section.setdefault("facts", []).extend(fact["id"] for fact in added)
    result["generated_at"] = datetime.now(UTC).isoformat()
    result["content_hash"] = content_digest(result)
    serialized = dumps_json(result)
    report_sha = hashlib.sha256(serialized.encode()).hexdigest()
    publication = {
        "schema_version": "1.0",
        "publication": "public",
        "report_file": "daily_report.json",
        "run_id": result["run_id"],
        "content_hash": result["content_hash"],
        "report_sha256": report_sha,
    }
    receipt = {
        "schema_version": "market_intel.index_close_enrichment.v1",
        "run_id": result["run_id"],
        "parent_report_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "parent_content_hash": original["content_hash"],
        "result_content_hash": result["content_hash"],
        "result_report_sha256": report_sha,
        "added_fact_ids": [fact["id"] for fact in added],
        "enriched_at": result["generated_at"],
    }
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, value in (
        ("daily_report.json", serialized),
        ("publication.json", dumps_json(publication)),
        ("index_close_parent.json", original_bytes.decode()),
        ("index_close_enrichment.json", dumps_json(receipt)),
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
    print(enrich_index_closes(args.input, args.manifest, args.output))


if __name__ == "__main__":
    main()
