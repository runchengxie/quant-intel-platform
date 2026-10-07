import copy
import json
from pathlib import Path

import pytest

from market_intel_publication.us_daily_status import (
    REQUIRED_MARKET_FACTS,
    report_status,
    status_index,
)


def _report():
    return {
        "publication": "public",
        "run_id": "daily-2026-10-06",
        "content_hash": "a" * 64,
        "source_status": {"research": {"quality": "degraded", "reason": "not_connected"}},
        "claims": [],
        "facts": [
            {"id": key, "value": 1.0, "observation_date": "2026-10-06", "quality": "ok"}
            for key in sorted(REQUIRED_MARKET_FACTS)
        ],
    }


def test_complete_market_excludes_optional_futures_and_preserves_payload():
    report = _report()
    before = copy.deepcopy(report)
    result = report_status(report)
    assert len(REQUIRED_MARKET_FACTS) == 32
    assert result["report_status"] == {
        "market": "complete",
        "research": "not_included",
        "publication": "published",
    }
    assert result["content_hash"] == report["content_hash"]
    assert not result["missing_market_facts"]
    assert report == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("value", True),
        ("value", float("nan")),
        ("value", float("inf")),
        ("observation_date", "2026-10-05"),
        ("quality", "lagged"),
    ],
)
def test_invalid_fact_is_a_market_gap(field, value):
    report = _report()
    report["facts"][0][field] = value
    assert report_status(report)["missing_market_facts"] == [report["facts"][0]["id"]]


def test_research_requires_review_and_source_backed_accepted_claim():
    report = _report()
    report["source_status"]["research"] = {"quality": "reviewed"}
    claim = {"status": "accepted", "sources": ["https://example.com"], "evidence_ids": ["event.1"]}
    report["events"] = [{"id": "event.1"}]
    report["claims"] = [claim]
    assert report_status(report)["report_status"]["research"] == "reviewed"
    claim["status"] = "pending"
    assert report_status(report)["report_status"]["research"] == "unknown"
    claim["status"] = "accepted"
    claim["sources"] = []
    assert report_status(report)["report_status"]["research"] == "unknown"


@pytest.mark.parametrize(
    "field,value",
    [("publication", "private"), ("content_hash", "invalid"), ("run_id", "daily-2026-13-01")],
)
def test_status_rejects_unbound_or_private_report(field, value):
    report = _report()
    report[field] = value
    with pytest.raises(ValueError):
        report_status(report)


def test_sidecar_schema_accepts_output_and_rejects_extra_fields():
    import jsonschema

    schema = json.loads(
        (Path(__file__).parents[1] / "schemas/public/us_daily_status.schema.json").read_text()
    )
    index = status_index([_report()])
    jsonschema.validate(index, schema)
    index["reports"][0]["private_path"] = "/secret"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(index, schema)
