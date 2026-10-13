import hashlib
import json
from pathlib import Path

import pytest

from daily_messenger.daily_report.serialization import content_digest


def bundle(tmp_path: Path) -> tuple[Path, Path]:
    payload = {
        "schema_version": "1.0",
        "as_of": "2026-10-02T23:00:00+00:00",
        "generated_at": "2026-10-03T00:00:00+00:00",
        "run_id": "daily-2026-10-02",
        "facts": [],
        "events": [],
        "claims": [],
        "sections": [],
        "source_status": {},
        "missing_sources": ["research"],
        "quality_summary": {"status": "degraded"},
        "private_note": "must not escape",
    }
    payload["content_hash"] = content_digest(payload)
    source = tmp_path / "daily_report.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    manifest = tmp_path / "publication.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "publication": "public",
                "report_file": source.name,
                "run_id": payload["run_id"],
                "content_hash": payload["content_hash"],
                "report_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return source, manifest


def test_brief_preserves_quality_and_only_public_projection(tmp_path):
    from market_intel_publication.agent_market_brief import read_market_brief

    source, manifest = bundle(tmp_path)
    before = source.read_bytes(), manifest.read_bytes()
    result = read_market_brief(source, manifest, expected_date="2026-10-02")
    assert result["schema_version"] == "quant.market_brief.v1"
    assert result["as_of"] == "2026-10-02T23:00:00+00:00"
    assert result["artifact_hash"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["data_quality"]["status"] == "degraded"
    assert result["report"]["missing_sources"] == ["research"]
    assert result["evidence_level"] == "descriptive"
    assert result["limitations"]
    assert "must not escape" not in json.dumps(result)
    assert before == (source.read_bytes(), manifest.read_bytes())


@pytest.mark.parametrize("change", ["hash", "internal", "schema", "date", "content"])
def test_brief_rejects_unverified_bundle(tmp_path, change):
    from market_intel_publication.agent_market_brief import read_market_brief

    source, manifest = bundle(tmp_path)
    data = json.loads(manifest.read_text())
    expected = "2026-10-02"
    if change == "hash":
        data["report_sha256"] = "0" * 64
    elif change == "internal":
        data["publication"] = "internal"
    elif change == "schema":
        data["schema_version"] = "9.0"
    elif change == "date":
        expected = "2026-10-03"
    else:
        payload = json.loads(source.read_text())
        payload["as_of"] = "2026-10-01T23:00:00+00:00"
        source.write_text(json.dumps(payload))
        data["report_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        read_market_brief(source, manifest, expected_date=expected)


def test_cli_error_emits_no_partial_report(tmp_path, capsys):
    from market_intel_publication.agent_market_brief import main

    source, manifest = bundle(tmp_path)
    arguments = ["--input", str(source), "--manifest", str(manifest), "--expected-date"]
    assert main([*arguments, "2026-10-02"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["run_id"] == "daily-2026-10-02"
    assert main([*arguments, "2026-10-03"]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert output.err


def test_brief_requires_linked_evidence(tmp_path):
    from market_intel_publication.agent_market_brief import read_market_brief

    source, manifest = bundle(tmp_path)
    payload = json.loads(source.read_text())
    payload["claims"] = [
        {
            "claim": "Unsubstantiated",
            "evidence_ids": ["missing"],
            "sources": ["https://example.test/source"],
        }
    ]
    payload["content_hash"] = content_digest(payload)
    source.write_text(json.dumps(payload))
    metadata = json.loads(manifest.read_text())
    metadata.update(
        content_hash=payload["content_hash"],
        report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="evidence"):
        read_market_brief(source, manifest, expected_date="2026-10-02")


def test_brief_preserves_fact_sources_and_reviewed_claim(tmp_path):
    from market_intel_publication.agent_market_brief import read_market_brief

    source, manifest = bundle(tmp_path)
    payload = json.loads(source.read_text())
    fact = {
        "id": "index.spx.change_percent",
        "metric": "daily_return",
        "instrument": "S&P 500",
        "value": 0.16,
        "unit": "percent",
        "source": "synthetic reviewed source",
        "source_url": "https://example.test/close",
        "source_time": "2026-10-02T20:12:00+00:00",
        "retrieved_at": "2026-10-02T23:00:00+00:00",
        "quality": "reviewed",
        "observation_date": "2026-10-02",
    }
    claim = {
        "claim": "Synthetic market rose",
        "evidence_ids": [fact["id"]],
        "sources": [fact["source_url"]],
        "status": "accepted",
        "confidence": "confirmed",
    }
    payload.update(facts=[fact], claims=[claim])
    payload["content_hash"] = content_digest(payload)
    source.write_text(json.dumps(payload))
    metadata = json.loads(manifest.read_text())
    metadata.update(
        content_hash=payload["content_hash"],
        report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    manifest.write_text(json.dumps(metadata))
    result = read_market_brief(source, manifest, expected_date="2026-10-02")
    assert result["report"]["claims"][0]["evidence_ids"] == [fact["id"]]
    assert result["report"]["facts"][0]["source_time"] == fact["source_time"]
    assert result["report"]["facts"][0]["source_url"] == fact["source_url"]


@pytest.mark.parametrize("expected", ["20261002", "2026-10-02", "invalid"])
def test_brief_rejects_invalid_or_naive_timestamps(tmp_path, expected):
    from market_intel_publication.agent_market_brief import read_market_brief

    source, manifest = bundle(tmp_path)
    payload = json.loads(source.read_text())
    payload["as_of"] = "2026-10-02T23:00:00"
    payload["content_hash"] = content_digest(payload)
    source.write_text(json.dumps(payload))
    metadata = json.loads(manifest.read_text())
    metadata.update(
        content_hash=payload["content_hash"],
        report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        read_market_brief(source, manifest, expected_date=expected)


def test_brief_rejects_id_only_legacy_event_evidence(tmp_path):
    from market_intel_publication.agent_market_brief import read_market_brief

    source, manifest = bundle(tmp_path)
    payload = json.loads(source.read_text())
    payload["events"] = [
        {
            "id": "legacy_event",
            "actual": "Synthetic event",
            "source_url": "https://example.test/news",
        }
    ]
    payload["claims"] = [
        {
            "claim": "Synthetic event",
            "evidence_ids": ["legacy_event"],
            "sources": ["https://example.test/news"],
        }
    ]
    payload["content_hash"] = content_digest(payload)
    source.write_text(json.dumps(payload))
    metadata = json.loads(manifest.read_text())
    metadata.update(
        content_hash=payload["content_hash"],
        report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="evidence"):
        read_market_brief(source, manifest, expected_date="2026-10-02")


@pytest.mark.parametrize("field,value", [("quality_summary", []), ("facts", [None])])
def test_cli_rejects_malformed_shapes_without_traceback(tmp_path, capsys, field, value):
    from market_intel_publication.agent_market_brief import main

    source, manifest = bundle(tmp_path)
    payload = json.loads(source.read_text())
    payload[field] = value
    source.write_text(json.dumps(payload))
    assert (
        main(["--input", str(source), "--manifest", str(manifest), "--expected-date", "2026-10-02"])
        == 2
    )
    output = capsys.readouterr()
    assert not output.out
    assert "rejected" in output.err


def test_brief_hashes_the_bytes_it_parses(tmp_path, monkeypatch):
    from market_intel_publication.agent_market_brief import read_market_brief

    source, manifest = bundle(tmp_path)
    original = source.read_bytes()
    read_bytes = Path.read_bytes
    read_text = Path.read_text
    reads = 0

    def replacing_read_bytes(path):
        nonlocal reads
        if path == source:
            reads += 1
            return original if reads == 1 else b"{}"
        return read_bytes(path)

    def replacing_read_text(path, *args, **kwargs):
        if path == source:
            return "{}"
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", replacing_read_bytes)
    monkeypatch.setattr(Path, "read_text", replacing_read_text)
    result = read_market_brief(source, manifest, expected_date="2026-10-02")
    assert result["artifact_hash"] == hashlib.sha256(original).hexdigest()
    assert result["report"]["run_id"] == "daily-2026-10-02"
    assert reads == 1
