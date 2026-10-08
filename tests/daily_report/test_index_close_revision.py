import copy
import hashlib
import json
from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report.index_close_revision import enrich_index_closes
from daily_messenger.daily_report.index_quotes import INDICES, fetch_index_facts
from daily_messenger.daily_report.serialization import content_digest, dumps_json
from daily_messenger.etl.types import QuoteSnapshot
from market_intel_publication.us_daily_contract import _read


def _input(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "daily_messenger.daily_report.index_quotes.fetch_yahoo_daily_snapshot",
        lambda symbol, *, target_date: QuoteSnapshot("2026-10-07", 1000.12, 0.25, symbol),
    )
    facts, _ = fetch_index_facts(datetime(2026, 10, 7, tzinfo=UTC).date())
    payload = {
        "schema_version": "1.0",
        "run_id": "daily-2026-10-07",
        "as_of": "2026-10-07T22:30:00+00:00",
        "generated_at": "2026-10-07T22:30:00+00:00",
        "facts": [
            json.loads(dumps_json(fact.to_dict()))
            for fact in facts
            if not fact.id.endswith(".close")
        ],
        "claims": [
            {
                "claim": "Retained research",
                "evidence_ids": ["event.1"],
                "sources": ["https://example.com/source"],
                "status": "accepted",
            }
        ],
        "events": [{"id": "event.1"}],
        "source_status": {"research": {"quality": "reviewed"}},
        "sections": [
            {
                "key": "market",
                "facts": [fact.id for fact in facts if not fact.id.endswith(".close")],
                "claims": [],
            }
        ],
    }
    return _write(tmp_path, payload)


def _write(tmp_path, payload):
    root = tmp_path / "original"
    root.mkdir(exist_ok=True)
    payload["content_hash"] = content_digest(payload)
    source = root / "daily_report.json"
    source.write_text(dumps_json(payload))
    manifest = root / "publication.json"
    manifest.write_text(
        dumps_json(
            {
                "schema_version": "1.0",
                "publication": "public",
                "report_file": source.name,
                "run_id": payload["run_id"],
                "content_hash": payload["content_hash"],
                "report_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    )
    return source, manifest


def test_index_enrichment_preserves_original_evidence_and_binds_receipt(tmp_path, monkeypatch):
    source, manifest = _input(tmp_path, monkeypatch)
    original = json.loads(source.read_text())
    raw = source.read_bytes()
    result = _read(enrich_index_closes(source, manifest, tmp_path / "stage"))
    assert result["facts"][:4] == original["facts"]
    assert len(result["facts"]) == 8
    for field in ("claims", "events", "source_status", "as_of", "run_id"):
        assert result[field] == original[field]
    assert result["content_hash"] != original["content_hash"]
    assert source.read_bytes() == raw
    receipt = json.loads((tmp_path / "stage/index_close_enrichment.json").read_text())
    assert receipt["parent_content_hash"] == original["content_hash"]
    assert receipt["result_content_hash"] == result["content_hash"]
    assert receipt["added_fact_ids"] == [f"index.{key}.close" for _, key, _ in INDICES]


@pytest.mark.parametrize("case", ["provider_failure", "conflict", "news_only", "bad_hash"])
def test_enrichment_fails_before_staging_on_unverified_parent_or_provider(
    tmp_path, monkeypatch, case
):
    source, manifest = _input(tmp_path, monkeypatch)
    payload = json.loads(source.read_text())
    if case == "news_only":
        payload["quality_summary"] = {"revision": "news_only"}
        source, manifest = _write(tmp_path, payload)
    elif case == "bad_hash":
        source.write_text(source.read_text().replace("0.25", "0.26"))
    else:
        monkeypatch.setattr(
            "daily_messenger.daily_report.index_quotes.fetch_yahoo_daily_snapshot",
            lambda symbol, *, target_date: QuoteSnapshot(
                "2026-10-06" if case == "provider_failure" else "2026-10-07", 1000.12, 0.35, symbol
            ),
        )
    raw = source.read_bytes()
    with pytest.raises(ValueError):
        enrich_index_closes(source, manifest, tmp_path / "stage")
    assert source.read_bytes() == raw
    assert not (tmp_path / "stage").exists()


def test_close_contract_rejects_incomplete_set_and_invalid_value(tmp_path, monkeypatch):
    source, manifest = _input(tmp_path, monkeypatch)
    enriched = _read(enrich_index_closes(source, manifest, tmp_path / "stage"))
    for value in (True, 0, -1, float("inf")):
        invalid = copy.deepcopy(enriched)
        invalid["facts"][-1]["value"] = value
        source, manifest = _write(tmp_path, invalid)
        with pytest.raises(ValueError):
            _read(source)
    enriched["facts"].pop()
    source, manifest = _write(tmp_path, enriched)
    with pytest.raises(ValueError):
        _read(source)
