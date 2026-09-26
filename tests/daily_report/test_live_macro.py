import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from daily_messenger.cli import main
from daily_messenger.daily_report.macro import fetch_us_macro_facts
from daily_messenger.daily_report.pipeline import run_daily_report
from daily_messenger.etl.fetchers.fred import FredFetchError, FredObservation

AS_OF = datetime(2026, 9, 24, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def offline_treasury(monkeypatch):
    monkeypatch.setattr(
        "daily_messenger.daily_report.macro.fetch_treasury_yield_observations",
        lambda _market_date: None,
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_index_facts",
        lambda _market_date: ([], ("^GSPC", "^DJI", "^IXIC", "^RUT")),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_cross_asset_facts",
        lambda _market_date: ([], ("BZ=F", "GC=F", "SI=F", "BTC=F")),
    )


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
    assert facts["treasury.10y.level_percent"].value == 4.23
    assert facts["treasury.10y.level_percent"].previous == 4.20
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
    assert "treasury.10y.level_percent" in report.sections[0].facts
    macro_section = next(section for section in report.sections if section.key == "macro")
    assert "macro.cpi_yoy" in macro_section.facts
    assert "index.spx.change_percent" not in facts


def test_live_report_marks_failed_macro_source_degraded(monkeypatch, tmp_path):
    def fail(_series_id, **_kwargs):
        raise FredFetchError("offline")

    monkeypatch.setattr("daily_messenger.daily_report.macro.fetch_observations", fail)
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_btc_spot_facts",
        lambda _date: ([], "all_spot_sources_unavailable"),
    )
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
    monkeypatch.setattr(
        "daily_messenger.daily_report.macro.fetch_treasury_yield_observations",
        lambda _market_date: None,
    )

    def fetch(_series_id, **_kwargs):
        return [
            FredObservation(date="2026-09-21", value=4.0),
            FredObservation(date="2026-09-22", value=4.1),
        ]

    monkeypatch.setattr("daily_messenger.daily_report.macro.fetch_observations", fetch)
    facts, status = fetch_us_macro_facts(AS_OF)

    assert status["rates"]["quality"] == "lagged"
    assert next(fact for fact in facts if fact.id == "treasury.10y.change_bp").quality == "lagged"


def test_official_treasury_same_day_overrides_lagged_fred(monkeypatch):
    requested = []

    def fetch(series_id, **_kwargs):
        requested.append(series_id)
        if series_id in {"DGS2", "DGS5", "DGS10", "DGS30"}:
            return [
                FredObservation(date="2026-09-21", value=4.0),
                FredObservation(date="2026-09-22", value=4.1),
            ]
        raise FredFetchError("not available")

    monkeypatch.setattr("daily_messenger.daily_report.macro.fetch_observations", fetch)
    monkeypatch.setattr(
        "daily_messenger.daily_report.macro.fetch_treasury_yield_observations",
        lambda _market_date: {
            tenor: {
                "level_percent": current,
                "previous_level_percent": current - change / 100,
                "change_bp": change,
            }
            for tenor, current, change in (
                ("2y", 4.85, 14.0),
                ("5y", 4.99, 16.0),
                ("10y", 5.11, 15.0),
                ("30y", 5.40, 11.0),
            )
        },
    )
    facts, status = fetch_us_macro_facts(AS_OF)
    rates = {fact.id: fact for fact in facts if fact.id.startswith("treasury.")}

    assert {
        tenor: rates[f"treasury.{tenor}.change_bp"].value for tenor in ("2y", "5y", "10y", "30y")
    } == {"2y": 14.0, "5y": 16.0, "10y": 15.0, "30y": 11.0}
    assert all(fact.observation_date == "2026-09-23" for fact in rates.values())
    assert all(fact.source == "US Treasury" for fact in rates.values())
    assert rates["treasury.10y.level_percent"].value == 5.11
    assert rates["treasury.10y.level_percent"].previous == 4.96
    assert status["rates"]["quality"] == "ok"
    assert not set(requested) & {"DGS2", "DGS5", "DGS10", "DGS30"}


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
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_cross_asset_facts",
        lambda _date: ([], ("BZ=F", "GC=F", "SI=F", "BTC=F")),
    )

    assert main(["daily-report", "--out", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / "daily_report.json").read_text())
    assert payload["facts"] == []
    assert payload["quality_summary"]["status"] == "degraded"


def test_cli_rejects_historical_live_date_without_vintage_sources(tmp_path):
    yesterday_ny = (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1)).date()

    assert main(["daily-report", "--date", yesterday_ny.isoformat(), "--out", str(tmp_path)]) != 0
    assert not (tmp_path / "daily_report.json").exists()


def test_cli_explicit_backfill_uses_requested_completed_market_day(monkeypatch, tmp_path):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 9, 25, 15, tzinfo=UTC)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr("daily_messenger.cli.datetime", FixedDateTime)
    captured = {}

    def run(cutoff, output, *, provider_config):
        captured.update(cutoff=cutoff, output=output, config=provider_config)
        return type("Report", (), {"run_id": "daily-2026-09-24"})()

    monkeypatch.setattr("daily_messenger.daily_report.pipeline.run_daily_report", run)

    result = main(["daily-report", "--date", "2026-09-24", "--backfill", "--out", str(tmp_path)])

    assert result == 0
    assert (
        captured["cutoff"].astimezone(ZoneInfo("America/New_York")).isoformat()
        == "2026-09-24T23:59:59-04:00"
    )
    assert captured["config"]["mode"] == "live"
    assert captured["config"]["backfill"] is True


def test_historical_report_marks_actual_generation_as_backfill(monkeypatch, tmp_path):
    fixed = datetime(2026, 9, 25, 15, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr("daily_messenger.daily_report.pipeline.datetime", FixedDateTime)
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_us_macro_facts",
        lambda _as_of: ([], {"macro": {"quality": "ok"}, "rates": {"quality": "ok"}}),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_cross_asset_facts",
        lambda _date: ([], ()),
    )

    report = run_daily_report(
        datetime(2026, 9, 24, 23, 59, 59, tzinfo=ZoneInfo("America/New_York")),
        tmp_path,
        provider_config={"mode": "live"},
    )

    assert report.run_id == "daily-2026-09-24"
    assert report.as_of == fixed
    assert report.quality_summary["revision"] == "historical_backfill"


def test_cli_accepts_recent_reviewed_revision_without_overriding_date(monkeypatch, tmp_path):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 9, 24, 8, tzinfo=UTC)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr("daily_messenger.cli.datetime", FixedDateTime)
    previous_ny = datetime(2026, 9, 23, tzinfo=ZoneInfo("America/New_York")).date()
    captured = {}

    def run(cutoff, output, *, provider_config):
        captured.update(cutoff=cutoff, output=output, config=provider_config)
        return type("Report", (), {"run_id": f"daily-{previous_ny.isoformat()}"})()

    monkeypatch.setattr("daily_messenger.daily_report.pipeline.run_daily_report", run)
    result = main(
        [
            "daily-report",
            "--date",
            previous_ny.isoformat(),
            "--out",
            str(tmp_path),
            "--reviewed-draft",
            "/tmp/draft.json",
            "--reviewed-decisions",
            "/tmp/review.json",
        ]
    )
    assert result == 0
    assert captured["cutoff"].astimezone(ZoneInfo("America/New_York")).date() == previous_ny
    assert captured["config"]["reviewed_draft"] == "/tmp/draft.json"
