from datetime import UTC, datetime

import pandas as pd
import pytest

from a_share_daily import asia_session as asia


def calendar(tmp_path, date="20261016"):
    path = tmp_path / "calendar.parquet"
    pd.DataFrame({"exchange": ["SSE"], "cal_date": [date], "is_open": [1]}).to_parquet(path)
    return path


def test_normal_day_and_provenance(tmp_path):
    payload = asia.build_asia_report(
        calendar(tmp_path),
        "20261016",
        quotes={
            key: {
                "date": "20261016",
                "close": 101,
                "previous_close": 100,
                "previous_date": "20261015",
                "retrieved_at": "2026-10-16T08:00:00+00:00",
            }
            for key in asia.MARKETS
        },
    )
    text = asia.render_asia_overview(payload)
    assert "| 香港 | 恒生指数 | 2026-10-16 | 101.00 | +1.00% | 已收盘 |" in text
    assert "### 亚洲市场概览" in text and "asia.close." in text


def test_pending_close_and_independent_failures(tmp_path):
    payload = asia.build_asia_report(
        calendar(tmp_path),
        "20261016",
        quotes={
            "HK": {
                "date": "20261016",
                "close": 101,
                "previous_close": 100,
                "previous_date": "20261015",
                "retrieved_at": "2026-10-16T08:00:00+00:00",
            },
            "JP": {
                "date": "20261016",
                "close": 101,
                "previous_close": 100,
                "previous_date": "20261015",
                "retrieved_at": "2026-10-16T06:30:00+00:00",
            },
            "KR": {"error": "source unavailable"},
        },
        now=datetime(2026, 10, 16, 7, tzinfo=UTC),
    )
    assert payload["markets"]["HK"]["status"] == "pending"
    assert payload["markets"]["JP"]["status"] == "open"
    assert payload["markets"]["KR"]["status"] == "missing"
    assert any("^KS11" in error for error in payload["errors"])


def test_stale_data_is_missing_with_warning(tmp_path):
    payload = asia.build_asia_report(
        calendar(tmp_path),
        "20261016",
        quotes={
            "HK": {
                "date": "20261015",
                "close": 101,
                "previous_close": 100,
                "previous_date": "20261015",
                "retrieved_at": "2026-10-16T08:00:00+00:00",
            },
        },
    )
    assert payload["markets"]["HK"]["status"] == "missing"
    assert any("stale" in error for error in payload["errors"])
    assert "101.00" not in asia.render_asia_overview(payload)


@pytest.mark.parametrize(
    ("date", "closed"), [("20261001", "HK"), ("20261012", "JP"), ("20261009", "KR")]
)
def test_independent_foreign_holidays(tmp_path, date, closed):
    payload = asia.build_asia_report(calendar(tmp_path, date), date, quotes={})
    assert payload["markets"][closed]["status"] == "closed"
    assert len(payload["markets"]) == 4


def test_fetch_validates_previous_session_and_timezone(monkeypatch):
    import yfinance

    class Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **_kwargs):
            if self.symbol == "^KS11":
                raise OSError("unavailable")
            dates = (
                ["2026-10-15", "2026-10-16"]
                if self.symbol == "^HSI"
                else ["2026-10-14", "2026-10-16"]
            )
            zone = "Asia/Hong_Kong" if self.symbol == "^HSI" else "Asia/Tokyo"
            return pd.DataFrame({"Close": [100, 101]}, index=pd.DatetimeIndex(dates, tz=zone))

    monkeypatch.setattr(yfinance, "Ticker", Ticker)
    quotes = asia._fetch_quotes(pd.Timestamp("2026-10-16"), dict.fromkeys(asia.MARKETS, True))
    assert quotes["HK"]["date"] == "20261016"
    assert "error" in quotes["JP"] and "error" in quotes["KR"]


def test_refresh_normal_day_uses_shared_module(tmp_path, monkeypatch):
    import json
    import time

    from a_share_daily import public_report_refresh as refresh

    path = calendar(tmp_path)
    monkeypatch.setattr(refresh, "is_a_share_session", lambda _: True)
    monkeypatch.setattr(
        asia, "session_status", lambda *_: dict.fromkeys(["CN", *asia.MARKETS], True)
    )
    payload = asia.build_asia_report(
        path,
        "20261016",
        quotes={
            "JP": {
                "date": "20261016",
                "close": 101,
                "previous_close": 100,
                "previous_date": "20261015",
                "retrieved_at": "2026-10-16T08:00:00+00:00",
            }
        },
    )
    monkeypatch.setattr(asia, "build_asia_report", lambda *_: payload)
    monkeypatch.setattr(refresh, "validate_evening", lambda *_: None)

    def call(_self, _name, _arguments, filename):
        output = tmp_path / filename
        output.write_text(
            json.dumps({}) if filename.endswith(".json") else "# A 股复盘（20261016）"
        )
        return output

    monkeypatch.setattr(refresh.OwnerRun, "call", call)
    run = refresh.OwnerRun(
        path, tmp_path, {"DATA_PLATFORM_ROOT": str(tmp_path)}, "20261016", time.monotonic() + 10
    )
    text = refresh.evening_markdown(run)
    assert "A 股复盘" in text and "### 亚洲市场概览" in text
    assert "日本 | 日经225 | 2026-10-16" in text
    assert "香港 | 恒生指数 | — | — | — | 当日数据缺失" in text


def test_symbol_errors_and_stale_dates_reach_top_level():
    from a_share_daily.cross_market import _annotate_equity_errors

    data = {
        "errors": [],
        "us_stocks": {
            "6857.T": {"error": "insufficient data"},
            "^HSI": {"as_of_date": "2026-10-15", "close": 100},
            "^N225": {"as_of_date": "2026-10-16", "close": 100},
        },
    }
    _annotate_equity_errors(data, "20261016")
    assert data["errors"] == ["6857.T: insufficient data"]
    assert any("^HSI" in item for item in data["_freshness_warnings"])


def test_v2_retains_and_checks_preceding_close(tmp_path):
    payload = asia.build_asia_report(
        calendar(tmp_path),
        "20261016",
        quotes={
            "HK": {
                "date": "20261016",
                "close": 101,
                "previous_close": 100,
                "previous_date": "20261015",
                "retrieved_at": "2026-10-16T08:00:00+00:00",
            },
        },
    )
    flags = dict.fromkeys(["CN", *asia.MARKETS], True)
    asia.validate_asia_report(payload, "20261016", flags)
    assert payload["markets"]["HK"]["previous_session"] == "2026-10-15"
    payload["markets"]["HK"]["previous_close"] = 99
    with pytest.raises(ValueError, match="return differs"):
        asia.validate_asia_report(payload, "20261016", flags)


@pytest.mark.parametrize("time", [6, 8])
def test_actual_close_boundary(tmp_path, time):
    payload = asia.build_asia_report(
        calendar(tmp_path),
        "20261016",
        quotes={
            key: {
                "date": "20261016",
                "close": 101,
                "previous_close": 100,
                "previous_date": "20261015",
                "retrieved_at": "2026-10-16T08:00:00+00:00",
            }
            for key in asia.MARKETS
        },
        now=datetime(2026, 10, 16, time, tzinfo=UTC),
    )
    assert payload["markets"]["HK"]["status"] == ("pending" if time == 6 else "open")
    assert payload["markets"]["JP"]["status"] == ("pending" if time == 6 else "open")


def test_retrieved_before_close_cannot_become_final_later(tmp_path):
    payload = asia.build_asia_report(
        calendar(tmp_path),
        "20261016",
        quotes={
            "HK": {
                "date": "20261016",
                "close": 101,
                "previous_close": 100,
                "previous_date": "20261015",
                "retrieved_at": "2026-10-16T07:59:59+00:00",
            },
        },
        now=datetime(2026, 10, 16, 8, 1, tzinfo=UTC),
    )
    row = payload["markets"]["HK"]
    assert row["status"] == "missing"
    assert row["reason_code"] == "retrieval_before_close_or_invalid"


def test_expired_pending_receipt_becomes_missing(tmp_path):
    payload = asia.build_asia_report(
        calendar(tmp_path), "20261016", quotes={}, now=datetime(2026, 10, 16, 7, tzinfo=UTC)
    )
    assert payload["markets"]["HK"]["status"] == "pending"
    asia.expire_pending_observations(payload, now=datetime(2026, 10, 16, 8, tzinfo=UTC))
    assert payload["markets"]["HK"]["status"] == "missing"
    assert payload["markets"]["HK"]["reason_code"] == "expired_pending"


def test_stale_diagnostic_preserves_observed_and_expected_dates(tmp_path):
    payload = asia.build_asia_report(
        calendar(tmp_path),
        "20261016",
        quotes={
            "HK": {"date": "20261015", "close": 101, "previous_close": 100},
        },
    )
    row = payload["markets"]["HK"]
    assert row["reason_code"] == "stale_session"
    assert row["observed_date"] == "2026-10-15"
    assert row["expected_date"] == "2026-10-16"
    assert "observed=2026-10-15" in asia.render_asia_overview(payload)


def test_requests_crossing_close_do_not_promote_early_hk_bar(tmp_path, monkeypatch):
    import yfinance

    clock = [datetime(2026, 10, 16, 7, 59, tzinfo=UTC)]
    requested = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    class Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **_kwargs):
            requested.append(self.symbol)
            clock[0] = datetime(2026, 10, 16, 8, 1, tzinfo=UTC)
            return pd.DataFrame(
                {"Close": [100, 101]},
                index=pd.DatetimeIndex(["2026-10-15", "2026-10-16"], tz="Asia/Tokyo"),
            )

    monkeypatch.setattr(asia, "datetime", Clock)
    monkeypatch.setattr(yfinance, "Ticker", Ticker)
    payload = asia.build_asia_report(calendar(tmp_path), "20261016")
    assert "^HSI" not in requested
    assert payload["markets"]["HK"]["status"] == "missing"
    assert payload["markets"]["HK"]["reason_code"] == "not_closed_at_request"
    assert payload["markets"]["JP"]["status"] == "open"
    monkeypatch.setattr(asia, "datetime", datetime)
    payload["markets"]["JP"]["retrieved_at"] = "2026-10-16T06:29:59+00:00"
    with pytest.raises(ValueError, match="retrieval"):
        asia.validate_asia_report(payload, "20261016", dict.fromkeys(["CN", *asia.MARKETS], True))


def test_preceding_session_diagnostic_keeps_expected_date():
    issue = asia._quote_error(
        {
            "reason_code": "preceding_session_missing_or_duplicate",
            "observed_date": "2026-10-14",
            "expected_date": "2026-10-15",
        },
        "preceding_session_missing_or_duplicate",
        pd.Timestamp("2026-10-16"),
    )
    assert issue.observed == "2026-10-14"
    assert issue.expected == "2026-10-15"
