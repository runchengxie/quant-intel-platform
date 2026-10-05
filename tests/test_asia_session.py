from pathlib import Path

import pandas as pd
import pytest

from a_share_daily.asia_session import (
    build_holiday_report,
    render_holiday_report,
    session_status,
    validate_holiday_report,
)


def calendar(tmp_path: Path) -> Path:
    path = tmp_path / "calendar.parquet"
    pd.DataFrame(
        {
            "exchange": ["SSE"] * 3,
            "cal_date": ["20261003", "20261004", "20261005"],
            "is_open": [0, 0, 0],
        }
    ).to_parquet(path)
    return path


def test_independent_holiday_sessions(tmp_path):
    assert session_status(calendar(tmp_path), "20261005") == {
        "CN": False,
        "HK": True,
        "JP": True,
        "KR": False,
    }
    assert not any(session_status(calendar(tmp_path), "20261004").values())


def test_calendar_missing_fails_closed(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        session_status(tmp_path / "absent.parquet", "20261005")


def test_holiday_quotes_cannot_relabel_stale_session(tmp_path):
    path = calendar(tmp_path)
    quotes = {
        "HK": {"date": "20261005", "close": 27000, "previous_close": 26000},
        "JP": {"date": "20261002", "close": 45000, "previous_close": 44000},
    }
    payload = build_holiday_report(path, "20261005", quotes=quotes)
    assert payload["markets"]["JP"]["status"] == "missing"
    assert payload["markets"]["HK"]["status"] == "open"
    assert payload["markets"]["HK"]["observation_date"] == "2026-10-05"
    validate_holiday_report(payload, "20261005", session_status(path, "20261005"))
    rendered = render_holiday_report(payload)
    assert "休市" in rendered and "27000" in rendered
    assert "45000" not in rendered and "涨停" not in rendered
    with pytest.raises(ValueError):
        build_holiday_report(path, "20261005", quotes={})


def test_reject_tampered_stale_observation_and_future_time(tmp_path):
    path = calendar(tmp_path)
    flags = session_status(path, "20261005")
    payload = build_holiday_report(
        path,
        "20261005",
        quotes={"HK": {"date": "20261005", "close": 27000, "previous_close": 26000}},
    )
    payload["markets"]["HK"]["observation_date"] = "2026-10-02"
    with pytest.raises(ValueError, match="stale"):
        validate_holiday_report(payload, "20261005", flags)
    payload["markets"]["HK"]["observation_date"] = "2026-10-05"
    payload["generated_at"] = "2099-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="timestamp"):
        validate_holiday_report(payload, "20261005", flags)


def test_cli_distinguishes_all_closed_and_calendar_error(tmp_path, capsys):
    from a_share_daily.asia_session import main

    path = calendar(tmp_path)
    assert main(["--calendar", str(path), "--date", "20261004"]) == 20
    assert main(["--calendar", str(path), "--date", "20261006"]) == 1
    assert (
        main(["--calendar", str(path), "--rows", "--start", "20261003", "--end", "20261005"]) == 0
    )
    assert "20261005" in capsys.readouterr().out


def test_cli_writes_durable_report(tmp_path, monkeypatch):
    from a_share_daily import asia_session

    path = calendar(tmp_path)
    quotes = {"HK": {"date": "20261005", "close": 27000, "previous_close": 26000}}
    monkeypatch.setattr(asia_session, "_fetch_quotes", lambda *_: quotes)
    output = tmp_path / "reports"
    assert (
        asia_session.main(
            ["--calendar", str(path), "--date", "20261005", "--report-output", str(output)]
        )
        == 0
    )
    assert (output / "20261005.json").is_file()
    assert "A 股今日休市" in (output / "20261005.md").read_text()
    assert not list(output.glob("*.tmp"))


def test_calendar_rejects_duplicates_and_open_cn_holiday(tmp_path):
    path = tmp_path / "calendar.parquet"
    pd.DataFrame(
        {"exchange": ["SSE", "SSE"], "cal_date": ["20261005", "20261005"], "is_open": [0, 1]}
    ).to_parquet(path)
    with pytest.raises(ValueError, match="ambiguous"):
        session_status(path, "20261005")
    pd.DataFrame({"exchange": ["SSE"], "cal_date": ["20261005"], "is_open": [1]}).to_parquet(path)
    with pytest.raises(ValueError, match="requires closed"):
        build_holiday_report(path, "20261005", quotes={})
