from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from a_share_daily.global_leadlag import aggregate_concept_signals

SH = ZoneInfo("Asia/Shanghai")


def test_observation_is_not_a_calibrated_prediction():
    row = aggregate_concept_signals({"NVDA": {"pct_chg": 4}})[0]
    assert row["signal"] == "neutral"
    assert row["movement"] == "up"
    assert row["evidence_status"] == "descriptive_unverified"
    assert row["mapping_version"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "bad", None])
def test_invalid_change_does_not_contaminate_average(value):
    assert aggregate_concept_signals({"NVDA": {"pct_chg": value}}) == []


def test_only_latest_completed_session_with_source_contributes():
    cutoff = datetime(2026, 10, 29, 8, 45, tzinfo=SH)
    quotes = {
        "NVDA": {
            "pct_chg": 3,
            "as_of_date": "2026-10-28",
            "source_url": "https://example.com/nvda",
        },
        "AMD": {"pct_chg": 99, "as_of_date": "2026-10-29", "source_url": "https://example.com/amd"},
        "AVGO": {
            "pct_chg": -99,
            "as_of_date": "2026-10-27",
            "source_url": "https://example.com/avgo",
        },
        "MSFT": {"pct_chg": 42},
    }
    rows = aggregate_concept_signals(quotes, decision_at=cutoff)
    assert rows
    assert all(row["avg_pct_chg"] == 3 for row in rows)
    assert all(row["evidence_status"] == "descriptive_session_checked" for row in rows)
    assert rows[0]["observations"][0]["source_url"] == "https://example.com/nvda"
    assert rows[0]["observations"][0]["source_time_utc"] == "2026-10-28T20:00:00+00:00"


def test_holiday_quote_is_current_and_future_retrieval_is_excluded():
    cutoff = datetime(2026, 7, 6, 8, 45, tzinfo=SH)
    quote = {"pct_chg": 2, "as_of_date": "2026-07-02", "source_url": "https://example.com/nvda"}
    assert aggregate_concept_signals({"NVDA": quote}, decision_at=cutoff)
    quote["observed_at_utc"] = "2026-07-06T01:00:00Z"
    assert aggregate_concept_signals({"NVDA": quote}, decision_at=cutoff) == []


@pytest.mark.parametrize(
    ("stamp", "stage", "session"),
    [
        ("2026-10-29T08:00:00+08:00", "preopen", "2026-10-29"),
        ("2026-10-29T11:00:00+08:00", "intraday", "2026-10-29"),
        ("2026-10-29T20:00:00+08:00", "postclose", "2026-10-30"),
        ("2026-10-31T08:00:00+08:00", "closed", "2026-11-02"),
        ("2026-10-01T08:00:00+08:00", "closed", "2026-10-08"),
    ],
)
def test_report_context_uses_exchange_calendar(stamp, stage, session):
    from a_share_daily.overseas_context import report_context

    context = report_context(datetime.fromisoformat(stamp))
    assert context["stage"] == stage
    assert context["next_session"] == session


def test_report_never_elevates_legacy_bullish_mapping():
    from a_share_daily.morning_report import render_morning_report

    report = render_morning_report(
        {
            "date": "20261029",
            "cross_market": {
                "global_lead_lag": [
                    {
                        "concept": "AI芯片",
                        "avg_pct_chg": 4,
                        "signal": "bullish",
                        "drivers": ["NVDA +4%"],
                    }
                ]
            },
        },
        generated_at=datetime(2026, 10, 29, 20, tzinfo=SH),
        locale="en-US",
    )
    assert "descriptive" in report.lower()
    assert "post-close" in report.lower()
    assert "2026-10-30" in report
    assert "[OK] AI芯片" not in report
    assert "unverified" in report.lower()


def test_default_clock_is_timezone_aware_on_a_utc_host(monkeypatch):
    from datetime import UTC

    from a_share_daily import morning_report

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            actual = datetime(2026, 10, 29, 0, 30, tzinfo=UTC)
            return actual.astimezone(tz) if tz else actual.replace(tzinfo=None)

    monkeypatch.setattr(morning_report, "datetime", Clock)
    report = morning_report.render_morning_report({"date": "20261029"})
    assert "2026-10-29 08:30" in report


@pytest.mark.parametrize("raw", [None, "failed", [], 42])
def test_invalid_quote_object_is_dropped_without_losing_report(raw):
    from a_share_daily.morning_report import render_morning_report

    assert aggregate_concept_signals({"NVDA": raw}) == []
    text = render_morning_report(
        {"date": "20261029", "cross_market": {"us_stocks": {"NVDA": raw}}},
        generated_at=datetime(2026, 10, 29, 8, tzinfo=SH),
    )
    assert "Overseas theme observations" in text


def test_prior_input_date_does_not_replace_report_decision_date():
    from a_share_daily.morning_report import render_morning_report

    text = render_morning_report(
        {
            "date": "20261028",
            "cross_market": {
                "us_stocks": {
                    "NVDA": {
                        "pct_chg": 4,
                        "as_of_date": "2026-10-28",
                        "source_url": "https://example.com/nvda",
                    }
                }
            },
        },
        generated_at=datetime(2026, 10, 29, 8, tzinfo=SH),
    )
    assert "quote:NVDA:2026-10-28" in text
    assert "2026-10-29T08:00:00+08:00" in text


def test_legacy_mapping_drops_forged_provenance_and_malformed_rows():
    from a_share_daily.morning_report import render_morning_report

    text = render_morning_report(
        {
            "date": "20261029",
            "cross_market": {
                "global_lead_lag": [
                    None,
                    {
                        "concept": "AI",
                        "avg_pct_chg": 4,
                        "signal": "bullish",
                        "evidence_status": "descriptive_session_checked",
                        "observations": [None, {}],
                    },
                    {"concept": "bad", "avg_pct_chg": "bad"},
                ]
            },
        },
        generated_at=datetime(2026, 10, 29, 8, tzinfo=SH),
    )
    assert "unverified" in text
    assert "[OK] AI" not in text


def test_cutoff_fetch_selects_completed_market_sessions(monkeypatch):
    import sys
    from types import SimpleNamespace

    import pandas as pd

    from a_share_daily import cross_market

    symbols = ["NVDA", "8035.T"]
    bars = pd.DataFrame(
        {("Close", symbol): [100, 102, 999] for symbol in symbols},
        index=pd.DatetimeIndex(["2026-10-27", "2026-10-28", "2026-10-29"]),
    )
    monkeypatch.setattr(cross_market, "US_SYMBOLS", symbols)
    monkeypatch.setattr(cross_market, "cooldown_active", lambda: False)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda *a, **k: bars))
    result = cross_market._fetch_us_stocks(
        "20261029", decision_at=datetime(2026, 10, 29, 8, 45, tzinfo=SH)
    )
    assert {row["as_of_date"] for row in result.values()} == {"2026-10-28"}
    assert {row["close"] for row in result.values()} == {102.0}


def test_morning_pipeline_default_date_uses_shanghai_clock(tmp_path, monkeypatch):
    from datetime import UTC

    from a_share_daily import pipeline

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            actual = datetime(2026, 10, 28, 23, 30, tzinfo=UTC)
            return actual.astimezone(tz) if tz else actual.replace(tzinfo=None)

    class StopBeforeReadingData(Exception):
        pass

    observed = []

    def stop(day):
        observed.append(day)
        raise StopBeforeReadingData

    monkeypatch.setattr(pipeline, "datetime", Clock)
    monkeypatch.setattr(pipeline, "_ensure_output_dir", lambda: None)
    monkeypatch.setattr(pipeline.D, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "step_data_freshness", stop)
    with pytest.raises(StopBeforeReadingData):
        pipeline.run_morning()
    assert observed == ["20261029"]


def test_english_report_localizes_correct_smh_product_label():
    from a_share_daily.morning_report import render_morning_report

    report = render_morning_report(
        {
            "date": "20261029",
            "cross_market": {
                "us_stocks": {
                    "SMH": {
                        "close": 100,
                        "pct_chg": 1,
                        "as_of_date": "2026-10-28",
                        "source_url": "https://example.org/smh",
                    }
                }
            },
        },
        generated_at=datetime(2026, 10, 29, 8, tzinfo=SH),
    )
    assert "VanEck Semiconductor ETF" in report
