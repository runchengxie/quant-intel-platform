import json
from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report.models import MarketFact
from daily_messenger.daily_report.serialization import content_digest, dumps_json
from daily_messenger.daily_report.treasury_revision import refresh_treasury_reference


def parent(tmp_path):
    payload = {
        "schema_version": "1.0",
        "run_id": "daily-2026-10-12",
        "as_of": "2026-10-13T00:00:00+00:00",
        "generated_at": "2026-10-13T00:00:00+00:00",
        "facts": [],
        "events": [],
        "claims": [],
        "sections": [],
        "source_status": {"research": {"quality": "degraded", "reason": "not_connected"}},
        "missing_sources": ["research", "rates_lag"],
        "quality_summary": {"status": "degraded"},
    }
    payload["facts"].append(
        {
            "id": "macro.cpi_yoy",
            "metric": "cpi_yoy",
            "instrument": "CPIAUCSL",
            "value": 3.4,
            "previous": None,
            "change": None,
            "unit": "percent",
            "source": "FRED",
            "source_url": "https://fred.stlouisfed.org/series/CPIAUCSL",
            "source_time": payload["as_of"],
            "retrieved_at": payload["as_of"],
            "quality": "ok",
            "observation_date": "2026-08-01",
        }
    )
    payload["content_hash"] = content_digest(payload)
    folder = tmp_path / "parent"
    folder.mkdir()
    report = folder / "daily_report.json"
    report.write_text(dumps_json(payload))
    import hashlib

    manifest = folder / "publication.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "publication": "public",
                "report_file": report.name,
                "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                "run_id": payload["run_id"],
                "content_hash": payload["content_hash"],
            }
        )
    )
    return report, manifest, payload


def mock_rates(monkeypatch, observed="2026-10-09"):
    read = datetime(2026, 10, 13, 1, tzinfo=UTC)
    facts = [
        MarketFact(
            id=f"treasury.{tenor}.{suffix}",
            metric=metric,
            instrument=f"US_TREASURY_{tenor.upper()}",
            value=value,
            previous=None,
            change=None,
            unit=unit,
            source="US Treasury",
            source_url=(
                "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                "daily-treasury-rates.csv/all/202610?_format=csv&field_tdr_date_value_month=202610"
                "&page=&type=daily_treasury_yield_curve"
            ),
            source_time=read,
            retrieved_at=read,
            quality="lagged",
            observation_date=observed,
        )
        for tenor in ("2y", "5y", "10y", "30y")
        for suffix, metric, unit, value in (
            ("level_percent", "yield_level", "percent", 5.24),
            ("change_bp", "yield_change", "basis_points", 2.0),
        )
    ]
    monkeypatch.setattr(
        "daily_messenger.daily_report.treasury_revision._rate_facts", lambda _asof: (facts, {})
    )


def test_reference_refresh_preserves_parent_and_nonrate_evidence(tmp_path, monkeypatch):
    source, manifest, original = parent(tmp_path)
    raw = source.read_bytes()
    mock_rates(monkeypatch)
    result = refresh_treasury_reference(
        source, manifest, tmp_path / "stage", refreshed_at=datetime(2026, 10, 13, 2, tzinfo=UTC)
    )
    revised = json.loads(result.read_text())
    assert source.read_bytes() == raw
    for field in ("claims", "events", "sections"):
        assert revised[field] == original[field]
    assert revised["source_status"]["research"] == original["source_status"]["research"]
    assert len(revised["facts"]) == 9
    assert [f for f in revised["facts"] if not f["id"].startswith("treasury.")] == original["facts"]
    assert revised["missing_sources"] == ["research"]
    assert revised["source_status"]["rates"]["reason"] == "holiday_reference"
    assert revised["source_status"]["rates"]["expected_observation_date"] == "2026-10-09"
    assert revised["content_hash"] == content_digest(revised)
    receipt = json.loads((result.parent / "treasury_refresh_receipt.json").read_text())
    assert receipt["parent_content_hash"] == original["content_hash"]
    assert receipt["original_as_of"] == original["as_of"]


def test_reference_refresh_does_not_admit_stale_data(tmp_path, monkeypatch):
    source, manifest, _ = parent(tmp_path)
    mock_rates(monkeypatch, "2026-10-08")
    with pytest.raises(ValueError, match="expected"):
        refresh_treasury_reference(source, manifest, tmp_path / "stage")
    assert not (tmp_path / "stage").exists()


def test_revision_module_cli_stages_without_promoting(tmp_path, monkeypatch, capsys):
    import sys
    from pathlib import Path

    from daily_messenger.daily_report.treasury_revision import main

    source, manifest, _ = parent(tmp_path)
    mock_rates(monkeypatch)
    output = tmp_path / "cli-stage"
    monkeypatch.setattr(
        sys,
        "argv",
        ["refresh", "--input", str(source), "--manifest", str(manifest), "--output", str(output)],
    )
    main()
    assert Path(capsys.readouterr().out.strip()) == output / "daily_report.json"
    assert (output / "treasury_refresh_parent.json").read_bytes() == source.read_bytes()
