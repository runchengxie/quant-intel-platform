import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from daily_messenger.cli import main
from daily_messenger.daily_report.macro import fetch_us_macro_facts
from daily_messenger.daily_report.pipeline import run_daily_report
from daily_messenger.etl.fetchers.fred import FredFetchError, FredObservation

AS_OF = datetime(2026, 9, 24, 1, tzinfo=UTC)


def test_live_report_uses_fred_observations_and_never_fixture_values(monkeypatch, tmp_path):
    observations = {
        "DGS2": [("2026-09-22", 4.01), ("2026-09-23", 4.05)],
        "DGS5": [("2026-09-22", 4.10), ("2026-09-23", 4.15)],
        "DGS10": [("2026-09-22", 4.20), ("2026-09-23", 4.23)],
        "DGS30": [("2026-09-22", 4.50), ("2026-09-23", 4.55)],
        "CPIAUCNS": [("2025-08-01", 320.0), ("2026-08-01", 332.8)],
        "PCEPI": [("2025-08-01", 125.0), ("2026-08-01", 127.5)],
        "UNRATE": [("2026-07-01", 4.1), ("2026-08-01", 4.2)],
        "PAYEMS": [("2026-07-01", 159000.0), ("2026-08-01", 159150.0)],
    }

    def fetch(series_id, **_kwargs):
        return [FredObservation(date=day, value=value) for day, value in observations[series_id]]

    monkeypatch.setattr("daily_messenger.daily_report.macro.fetch_observations", fetch)
    report = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "live"})
    facts = {fact.id: fact for fact in report.facts}

    assert facts["treasury.2y.change_bp"].value == 4.0
    assert facts["treasury.10y.change_bp"].value == 3.0
    assert facts["macro.cpi_yoy"].value == 4.0
    assert facts["macro.pce_yoy"].value == 2.0
    assert facts["macro.unemployment_rate"].value == 4.2
    assert facts["macro.payroll_change_thousands"].value == 150.0
    assert facts["macro.cpi_yoy"].source_url == "https://fred.stlouisfed.org/series/CPIAUCNS"
    assert facts["macro.cpi_yoy"].observation_date == "2026-08-01"
    assert facts["treasury.10y.change_bp"].observation_date == "2026-09-23"
    assert facts["macro.cpi_yoy"].source_time == facts["macro.cpi_yoy"].retrieved_at
    assert facts["macro.cpi_yoy"].source_time <= report.as_of
    assert all(fact.source_url for fact in report.facts)
    assert report.source_status["macro"]["quality"] == "ok"
    assert report.quality_summary["status"] == "degraded"
    assert "quotes" in report.missing_sources
    assert "treasury.2y.change_bp" in report.sections[0].facts
    assert "macro.cpi_yoy" in report.sections[2].facts
    assert "index.spx.change_percent" not in facts


def test_live_report_marks_failed_macro_source_degraded(monkeypatch, tmp_path):
    def fail(_series_id, **_kwargs):
        raise FredFetchError("offline")

    monkeypatch.setattr("daily_messenger.daily_report.macro.fetch_observations", fail)
    report = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "live"})

    assert report.facts == ()
    assert report.source_status["macro"]["quality"] == "degraded"
    assert report.quality_summary["status"] == "degraded"
    assert "fred" in report.missing_sources


def test_stale_yield_is_not_presented_as_current(monkeypatch):
    def fetch(_series_id, **_kwargs):
        return [
            FredObservation(date="2026-09-14", value=4.0),
            FredObservation(date="2026-09-15", value=4.1),
        ]

    monkeypatch.setattr("daily_messenger.daily_report.macro.fetch_observations", fetch)
    facts, status = fetch_us_macro_facts(AS_OF)

    assert not any(fact.id.startswith("treasury.") for fact in facts)
    assert status["rates"]["quality"] == "degraded"


def test_previous_day_yield_is_marked_lagged(monkeypatch):
    def fetch(_series_id, **_kwargs):
        return [
            FredObservation(date="2026-09-21", value=4.0),
            FredObservation(date="2026-09-22", value=4.1),
        ]

    monkeypatch.setattr("daily_messenger.daily_report.macro.fetch_observations", fetch)
    facts, status = fetch_us_macro_facts(AS_OF)

    assert status["rates"]["quality"] == "lagged"
    assert next(fact for fact in facts if fact.id == "treasury.10y.change_bp").quality == "lagged"


def test_pce_yoy_uses_prior_year_when_latest_release_is_two_months_old(monkeypatch):
    def fetch(series_id, *, start=None, **_kwargs):
        if series_id != "PCEPI":
            raise FredFetchError("not available")
        return [
            row
            for row in (
                FredObservation(date="2025-07-01", value=125.0),
                FredObservation(date="2026-07-01", value=127.5),
            )
            if start is None or row.date >= start
        ]

    monkeypatch.setattr("daily_messenger.daily_report.macro.fetch_observations", fetch)
    facts, _status = fetch_us_macro_facts(AS_OF)

    assert next(fact for fact in facts if fact.id == "macro.pce_yoy").value == 2.0


def test_cli_daily_report_does_not_publish_fixture_values(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_us_macro_facts",
        lambda _as_of: ([], {"macro": {"quality": "degraded"}, "rates": {"quality": "degraded"}}),
    )

    assert main(["daily-report", "--out", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / "daily_report.json").read_text())
    assert payload["facts"] == []
    assert payload["quality_summary"]["status"] == "degraded"


def test_cli_rejects_historical_live_date_without_vintage_sources(tmp_path):
    yesterday_ny = (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1)).date()

    assert main(["daily-report", "--date", yesterday_ny.isoformat(), "--out", str(tmp_path)]) != 0
    assert not (tmp_path / "daily_report.json").exists()
