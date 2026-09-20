import json
from pathlib import Path


def test_public_daily_report_contains_no_credentials():
    fixture = Path("tests/fixtures/public/daily_report.json")
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    serialized = json.dumps(payload)
    assert "API_KEY" not in serialized
    assert "auth.json" not in serialized


def test_public_daily_report_has_source_and_cutoff():
    payload = json.loads(Path("tests/fixtures/public/daily_report.json").read_text(encoding="utf-8"))
    assert payload["as_of"]
    assert payload["schema_version"]
    assert all(claim["evidence_ids"] for claim in payload["claims"])
