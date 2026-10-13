from datetime import date

import pytest

from daily_messenger.daily_report.treasury_calendar import expected_observation_date


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        ("2026-10-12", "2026-10-09"),
        ("2026-11-11", "2026-11-10"),
        ("2026-10-13", "2026-10-13"),
        ("2026-10-11", "2026-10-09"),
        ("2026-04-03", "2026-04-03"),
        ("2026-07-03", "2026-07-02"),
        ("2027-03-26", "2027-03-25"),
        ("2026-01-01", "2025-12-31"),
    ],
)
def test_expected_treasury_observation_day(day, expected):
    assert expected_observation_date(date.fromisoformat(day)).isoformat() == expected


def test_calendar_does_not_guess_unreviewed_years():
    with pytest.raises(ValueError, match="coverage"):
        expected_observation_date(date(2028, 10, 9))


def test_calendar_installed_module_cli():
    import json
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "daily_messenger.daily_report.treasury_calendar",
            "--date",
            "2026-10-12",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "market_intel.treasury_session.v1"
    assert payload["session"] == "closed"
    assert payload["expected_observation_date"] == "2026-10-09"
    assert payload["calendar_source"].startswith("https://www.sifma.org/")


def test_official_holiday_reference_contract_rejects_older_date():
    from market_intel_publication.us_daily_contract import _valid_market_fact

    row = {
        "id": "treasury.10y.change_bp",
        "value": 2.0,
        "metric": "yield_change",
        "unit": "basis_points",
        "observation_date": "2026-10-09",
        "quality": "lagged",
        "source_url": (
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/all/202610?_format=csv&field_tdr_date_value_month=202610"
            "&page=&type=daily_treasury_yield_curve"
        ),
    }
    assert _valid_market_fact(row, "2026-10-12")
    row["observation_date"] = "2026-10-08"
    assert not _valid_market_fact(row, "2026-10-12")


def test_calendar_main_and_reference_rendering(monkeypatch, capsys):
    import json
    import sys

    from daily_messenger.daily_report.treasury_calendar import main
    from market_intel_publication.import_market_daily_report import (
        _macro_table,
        _source_status_lines,
    )

    monkeypatch.setattr(sys, "argv", ["calendar", "--date", "2026-10-12"])
    main()
    assert json.loads(capsys.readouterr().out)["expected_observation_date"] == "2026-10-09"
    fact = {
        "id": "treasury.10y.change_bp",
        "value": 2.0,
        "quality": "lagged",
        "observation_date": "2026-10-09",
        "source": "US Treasury",
        "source_url": "https://example.test/curve",
    }
    assert "最近交易日变动" in "\n".join(_macro_table([fact]))
    text = "\n".join(
        _source_status_lines(
            {
                "rates": {
                    "quality": "lagged",
                    "reason": "holiday_reference",
                    "expected_observation_date": "2026-10-09",
                }
            }
        )
    )
    assert "美债休市" in text and "2026-10-09" in text


def test_packaged_calendar_artifact_matches_reviewed_sessions():
    import json
    from importlib.resources import files

    from daily_messenger.daily_report.treasury_calendar import CALENDAR_VERSION, END, START

    payload = json.loads(
        files("daily_messenger.daily_report").joinpath("data/treasury_sessions_v1.json").read_text()
    )
    assert payload["schema_version"] == "market_intel.treasury_calendar.v1"
    assert payload["calendar_version"] == CALENDAR_VERSION
    assert len(payload["expected_observations"]) == (END - START).days + 1
    for day, expected in payload["expected_observations"].items():
        assert expected_observation_date(date.fromisoformat(day)).isoformat() == expected
