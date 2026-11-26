from datetime import date

import pytest


def test_holiday_and_bond_only_sessions():
    from daily_messenger.daily_report.equity_calendar import (
        expected_observation_date,
        session_close,
    )

    assert expected_observation_date(date(2026, 11, 26)) == date(2026, 11, 25)
    assert expected_observation_date(date(2026, 10, 12)) == date(2026, 10, 12)
    assert expected_observation_date(date(2026, 11, 11)) == date(2026, 11, 11)
    assert session_close(date(2026, 11, 27)).isoformat() == "2026-11-27T18:00:00+00:00"
    with pytest.raises(ValueError, match="coverage"):
        expected_observation_date(date(2030, 1, 1))


def test_holiday_index_requests_exact_expected_session(monkeypatch):
    from daily_messenger.daily_report.index_quotes import fetch_index_facts
    from daily_messenger.etl.types import QuoteSnapshot

    def fetch(symbol, *, target_date, expected_previous_date=None):
        assert target_date == date(2026, 11, 25)
        assert expected_previous_date == date(2026, 11, 24)
        return QuoteSnapshot("2026-11-25", 123.45, 0.25, symbol)

    monkeypatch.setattr(
        "daily_messenger.daily_report.index_quotes.fetch_yahoo_daily_snapshot", fetch
    )
    facts, missing = fetch_index_facts(date(2026, 11, 26))
    assert not missing
    assert len(facts) == 8
    assert all(f.quality == "lagged" and f.observation_date == "2026-11-25" for f in facts)


@pytest.mark.parametrize(
    ("value", "expected"), [(41.235, "41.24"), (-41.235, "-41.24"), (-0.001, "0.00")]
)
def test_decimal_display(value, expected):
    from daily_messenger.daily_report.display import format_decimal

    assert format_decimal(value) == expected


def test_public_reference_requires_independent_calendar_metadata():
    from daily_messenger.daily_report.equity_calendar import session_metadata
    from market_intel_publication.us_daily_contract import _valid_market_fact

    fact = {
        "id": "equity.msft.close",
        "instrument": "MSFT",
        "metric": "stock_close",
        "unit": "USD/share",
        "value": 41.235,
        "source": "Yahoo Finance",
        "source_url": "https://finance.yahoo.com/quote/MSFT/history/",
        "quality": "lagged",
        "observation_date": "2026-11-25",
    }
    status = session_metadata(date(2026, 11, 26)) | {"reason": "holiday_reference"}
    assert _valid_market_fact(fact, "2026-11-26", equity_status=status)
    assert not _valid_market_fact(fact, "2026-11-27", equity_status=status)
    assert not _valid_market_fact(
        fact, "2026-11-26", equity_status=status | {"calendar_version": "forged"}
    )
    assert not _valid_market_fact(
        fact | {"observation_date": "2026-11-24"}, "2026-11-26", equity_status=status
    )


def test_public_export_preserves_holiday_session_evidence():
    from daily_messenger.daily_report.equity_calendar import session_metadata
    from market_intel_publication.us_daily_contract import _public_payload

    status = session_metadata(date(2026, 11, 26)) | {
        "reason": "holiday_reference",
        "quality": "lagged",
    }
    payload = {
        "schema_version": "1.0",
        "run_id": "daily-2026-11-26",
        "as_of": "2026-11-26T23:00:00Z",
        "generated_at": "2026-11-26T23:00:00Z",
        "facts": [],
        "claims": [],
        "source_status": {"quotes": status, "equities": status},
    }
    public = _public_payload(payload, {"report_sha256": "test"})
    assert public["source_status"]["quotes"]["calendar_version"] == status["calendar_version"]
    assert public["source_status"]["equities"]["observation_date"] == "2026-11-25"


def test_alpaca_early_close_uses_real_session_close(monkeypatch):
    from daily_messenger.daily_report import equity_quotes

    def request(url, *, params, headers):
        assert params["end"] == "2026-11-27T18:00:00+00:00"
        return {
            "bars": {
                "MSFT": [
                    {"t": "2026-11-25T05:00:00Z", "c": 100},
                    {"t": "2026-11-27T05:00:00Z", "c": 101},
                ]
            }
        }

    monkeypatch.setattr(equity_quotes, "request_json", request)
    # Set a deterministic completed time, including when this runs before the session.
    from datetime import UTC, datetime

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 27, 18, 15, tzinfo=UTC)

    monkeypatch.setattr(equity_quotes, "datetime", Clock)
    assert (
        equity_quotes._fetch_alpaca_sip_snapshot("MSFT", date(2026, 11, 27), "key", "secret").close
        == 101
    )


def test_public_status_counts_calendar_verified_equity_references():
    from daily_messenger.daily_report.equity_calendar import session_metadata
    from market_intel_publication.us_daily_status import report_status

    status = session_metadata(date(2026, 11, 26)) | {"reason": "holiday_reference"}
    row = {
        "id": "equity.msft.close",
        "value": 41.235,
        "observation_date": "2026-11-25",
        "quality": "lagged",
    }
    report = {
        "publication": "public",
        "run_id": "daily-2026-11-26",
        "content_hash": "a" * 64,
        "facts": [row],
        "source_status": {"equities": status},
    }
    assert "equity.msft.close" not in report_status(report)["missing_market_facts"]
    report["source_status"]["equities"] = status | {"calendar_version": "forged"}
    assert "equity.msft.close" in report_status(report)["missing_market_facts"]


def test_markdown_decimal_half_increment_and_last_session_label():
    from daily_messenger.daily_report.equity_calendar import session_metadata
    from market_intel_publication.import_market_daily_report import _markdown_fact_lines

    common = {
        "instrument": "MSFT",
        "source": "Yahoo Finance",
        "source_url": "https://finance.yahoo.com/quote/MSFT/history/",
        "quality": "lagged",
        "observation_date": "2026-11-25",
    }
    rows = [
        common
        | {
            "id": "equity.msft.close",
            "metric": "stock_close",
            "unit": "USD/share",
            "value": 41.235,
        },
        common
        | {
            "id": "equity.msft.change_percent",
            "metric": "daily_return",
            "unit": "percent",
            "value": -1.005,
        },
    ]
    payload = {
        "run_id": "daily-2026-11-26",
        "facts": rows,
        "source_status": {
            "equities": session_metadata(date(2026, 11, 26)) | {"reason": "holiday_reference"}
        },
    }
    rendered = "\n".join(_markdown_fact_lines(payload, "equities"))
    assert "41.24" in rendered and "-1.01%" in rendered
    assert "最近交易日涨跌" in rendered and "2026-11-25" in rendered


def test_holiday_equities_keep_actual_observation_and_pair(monkeypatch):
    from daily_messenger.daily_report import equity_quotes
    from daily_messenger.etl.types import QuoteSnapshot

    monkeypatch.setattr(
        equity_quotes,
        "fetch_yahoo_daily_snapshot",
        lambda symbol, *, target_date, expected_previous_date=None: QuoteSnapshot(
            target_date.isoformat(), 41.235, -1.005, symbol
        ),
    )
    facts, missing = equity_quotes.fetch_equity_facts(date(2026, 11, 26))
    assert not missing and len(facts) == 12
    assert all(f.quality == "lagged" and f.observation_date == "2026-11-25" for f in facts)
    assert facts[0].value == 41.235


def test_holiday_index_table_labels_last_session_return():
    from daily_messenger.daily_report.equity_calendar import session_metadata
    from market_intel_publication.import_market_daily_report import _markdown_fact_lines

    rows = [
        {
            "id": "index.spx.change_percent",
            "instrument": "S&P 500",
            "metric": "daily_return",
            "unit": "percent",
            "value": 1,
            "quality": "lagged",
            "observation_date": "2026-11-25",
            "source": "Yahoo Finance",
            "source_url": "https://finance.yahoo.com/quote/%5EGSPC/history/",
        }
    ]
    payload = {
        "run_id": "daily-2026-11-26",
        "facts": rows,
        "source_status": {
            "quotes": session_metadata(date(2026, 11, 26)) | {"reason": "holiday_reference"}
        },
    }
    assert "最近交易日涨跌" in "\n".join(_markdown_fact_lines(payload, "market"))


def test_public_status_counts_only_verified_treasury_holiday_reference():
    from daily_messenger.daily_report.treasury_calendar import session_metadata
    from market_intel_publication.us_daily_status import report_status

    status = session_metadata(date(2026, 11, 26)) | {
        "reason": "holiday_reference",
        "observation_date": "2026-11-25",
    }
    fact = {
        "id": "treasury.10y.level_percent",
        "value": 4.1,
        "quality": "lagged",
        "observation_date": "2026-11-25",
    }
    report = {
        "publication": "public",
        "run_id": "daily-2026-11-26",
        "content_hash": "a" * 64,
        "facts": [fact],
        "source_status": {"rates": status},
    }
    assert fact["id"] not in report_status(report)["missing_market_facts"]
    fact["observation_date"] = "2026-11-24"
    assert fact["id"] in report_status(report)["missing_market_facts"]


def test_yahoo_exact_previous_session_cannot_skip_missing_bar(monkeypatch):
    from datetime import UTC, datetime

    from daily_messenger.etl.fetchers import quotes

    stamps = [
        int(datetime(2026, 11, 23, 14, 30, tzinfo=UTC).timestamp()),
        int(datetime(2026, 11, 25, 14, 30, tzinfo=UTC).timestamp()),
    ]
    monkeypatch.setattr(
        quotes,
        "_fetch_yahoo_chart",
        lambda symbol: {
            "meta": {"exchangeTimezoneName": "America/New_York"},
            "timestamp": stamps,
            "indicators": {"quote": [{"close": [100, 101]}]},
        },
    )
    with pytest.raises(RuntimeError, match="previous session"):
        quotes.fetch_yahoo_daily_snapshot(
            "MSFT", target_date=date(2026, 11, 25), expected_previous_date=date(2026, 11, 24)
        )


def test_alpaca_exact_previous_session_cannot_skip_missing_bar(monkeypatch):
    from daily_messenger.daily_report import equity_quotes

    monkeypatch.setattr(
        equity_quotes,
        "request_json",
        lambda *args, **kwargs: {
            "bars": {
                "MSFT": [
                    {"t": "2026-11-23T05:00:00Z", "c": 100},
                    {"t": "2026-11-25T05:00:00Z", "c": 101},
                ]
            }
        },
    )
    with pytest.raises(ValueError, match="previous session"):
        equity_quotes._fetch_alpaca_sip_snapshot("MSFT", date(2026, 11, 25), "key", "secret")


@pytest.mark.parametrize(
    ("fact_id", "instrument", "metric", "unit", "url"),
    [
        (
            "equity.msft.close",
            "MSFT",
            "stock_close",
            "USD/share",
            "https://finance.yahoo.com/quote/MSFT/history/",
        ),
        (
            "index.spx.close",
            "S&P 500",
            "index_close",
            "points",
            "https://finance.yahoo.com/quote/%5EGSPC/history/",
        ),
    ],
)
def test_closed_equity_date_rejects_forged_same_day_fresh(fact_id, instrument, metric, unit, url):
    from daily_messenger.daily_report.equity_calendar import session_metadata
    from market_intel_publication.us_daily_contract import _valid_market_fact
    from market_intel_publication.us_daily_status import report_status

    fact = {
        "id": fact_id,
        "instrument": instrument,
        "metric": metric,
        "unit": unit,
        "source": "Yahoo Finance",
        "source_url": url,
        "value": 100,
        "quality": "ok",
        "observation_date": "2026-11-26",
    }
    status = session_metadata(date(2026, 11, 26)) | {"reason": "holiday_reference"}
    assert not _valid_market_fact(fact, "2026-11-26", equity_status=status)
    report = {
        "publication": "public",
        "run_id": "daily-2026-11-26",
        "content_hash": "a" * 64,
        "facts": [fact],
        "source_status": {"equities": status, "quotes": status},
    }
    # Index closes are optional, so inspect its required return analogue for status.
    if fact_id.startswith("index."):
        fact["id"] = "index.spx.change_percent"
    assert fact["id"] in report_status(report)["missing_market_facts"]
