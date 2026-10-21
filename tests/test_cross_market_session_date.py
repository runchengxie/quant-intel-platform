"""Synthetic session selection and explicit commodity failure propagation."""

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from a_share_daily import cross_market, fallback_fetch


def frame(symbol, dates, values=None):
    return pd.DataFrame(
        {("Close", symbol): values if values is not None else range(100, 100 + len(dates))},
        index=pd.DatetimeIndex(dates),
    )


def install_run(monkeypatch, symbols, downloads, commodities=None):
    calls = []

    def download(tickers, **kwargs):
        calls.append((tickers, kwargs))
        return downloads[min(len(calls) - 1, len(downloads) - 1)]

    monkeypatch.setattr(cross_market, "US_SYMBOLS", symbols)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    monkeypatch.setenv("CROSS_MARKET_FORCE_LIVE", "1")
    monkeypatch.setattr(cross_market, "_fetch_aaii", lambda: None)
    monkeypatch.setattr(cross_market, "_fetch_cboe_into", lambda _result: None)
    monkeypatch.setattr(cross_market, "_map_us_into", lambda _result: None)
    monkeypatch.setattr(cross_market, "_map_commodities_into", lambda _result: None)
    monkeypatch.setattr(cross_market, "_fetch_commodities", lambda _date=None: commodities or {})
    monkeypatch.setattr(cross_market, "_fetch_korea_signals", lambda _date: ({}, {}, {}))
    monkeypatch.setattr(cross_market, "_fetch_macros", lambda _date=None: {})
    return calls


@pytest.mark.parametrize(("symbol", "expected_pct"), [("^HSI", 12.22), ("^N225", 1), ("^KS11", 1)])
def test_target_session_excludes_next_day_bar(monkeypatch, symbol, expected_pct):
    # HK's preceding session is Oct 16 because Oct 19 is Chung Yeung Festival.
    install_run(
        monkeypatch,
        [symbol],
        [
            frame(
                symbol,
                ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"],
                [90, 100, 101, 102],
            )
        ],
    )
    data = cross_market.run("20261020")
    assert data["us_stocks"][symbol]["as_of_date"] == "2026-10-20"
    assert data["us_stocks"][symbol]["close"] == 101
    assert data["us_stocks"][symbol]["pct_chg"] == expected_pct
    assert not data.get("_freshness_warnings")


@pytest.mark.parametrize(
    ("symbol", "target", "dates", "expected"),
    [
        ("^HSI", "20261001", ["2026-09-29", "2026-09-30", "2026-10-02"], "2026-09-30"),
        ("^N225", "20261012", ["2026-10-08", "2026-10-09", "2026-10-13"], "2026-10-09"),
        ("^KS11", "20261009", ["2026-10-07", "2026-10-08", "2026-10-12"], "2026-10-08"),
        ("SPY", "20261018", ["2026-10-15", "2026-10-16", "2026-10-19"], "2026-10-16"),
    ],
)
def test_foreign_holiday_and_weekend_use_each_markets_calendar(
    monkeypatch, symbol, target, dates, expected
):
    install_run(monkeypatch, [symbol], [frame(symbol, dates)])
    quote = cross_market.run(target)["us_stocks"][symbol]
    assert quote["as_of_date"] == expected
    assert quote["close"] == 101
    assert quote["pct_chg"] == 1


@pytest.mark.parametrize(
    "dates",
    [
        ["2026-10-19", "2026-10-21"],
        ["2026-10-16", "2026-10-20", "2026-10-21"],
        ["2026-10-19", "2026-10-20", "2026-10-20", "2026-10-21"],
    ],
)
def test_missing_target_or_preceding_session_remains_error(monkeypatch, dates):
    install_run(monkeypatch, ["^N225"], [frame("^N225", dates)])
    data = cross_market.run("20261020")
    assert "error" in data["us_stocks"]["^N225"]
    assert "close" not in data["us_stocks"]["^N225"]
    assert any("^N225" in error for error in data["errors"])


def test_session_labels_use_exchange_timezone(monkeypatch):
    dates = pd.date_range("2026-10-18 15:00", periods=3, tz="UTC")
    install_run(monkeypatch, ["^N225"], [frame("^N225", dates)])
    quote = cross_market.run("20261020")["us_stocks"]["^N225"]
    assert quote["as_of_date"] == "2026-10-20"
    assert quote["close"] == 101


def test_batch_and_serial_retry_share_target_window(monkeypatch):
    batch = pd.concat(
        [
            frame(
                "^HSI",
                ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"],
                [90, float("nan"), float("nan"), 200],
            ),
            frame(
                "SPY",
                ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"],
                [float("nan"), 100, 102, float("nan")],
            ),
        ],
        axis=1,
    )
    calls = install_run(
        monkeypatch,
        ["^HSI", "SPY"],
        [
            batch,
            frame(
                "^HSI",
                ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"],
                [90, float("nan"), 101, 102],
            ),
        ],
    )
    data = cross_market.run("20261020")
    assert len(calls) == 2
    assert calls[1][0] == ["^HSI"]
    for _, kwargs in calls:
        assert kwargs.get("start") == "2026-10-16"
        assert kwargs.get("end") == "2026-10-21"
        assert kwargs.get("ignore_tz") is True
        assert "period" not in kwargs
    assert calls[1][1]["threads"] is False
    assert calls[1][1]["timeout"] == 10
    assert data["us_stocks"]["SPY"]["close"] == 102
    assert data["us_stocks"]["^HSI"]["as_of_date"] == "2026-10-20"


@pytest.mark.parametrize(
    ("commodities", "expected"),
    [
        (
            {symbol: {"error": "insufficient data"} for symbol in ["GC=F", "SLV", "GLD"]},
            ["GC=F: insufficient data", "GLD: insufficient data", "SLV: insufficient data"],
        ),
        ({"error": "source unavailable"}, ["commodities: source unavailable"]),
        ({}, []),
    ],
)
def test_only_actual_commodity_failures_reach_partial_status(monkeypatch, commodities, expected):
    install_run(monkeypatch, ["SPY"], [frame("SPY", ["2026-10-19", "2026-10-20"])], commodities)
    data = cross_market.run("20261020")
    assert data["errors"] == expected
    monkeypatch.setattr(fallback_fetch, "run", lambda *_args, **_kwargs: data)
    monkeypatch.setattr(sys, "argv", ["fallback_fetch", "--date", "20261020"])
    assert fallback_fetch.main() == (1 if expected else 0)


def test_commodity_quotes_include_actual_observation_date(monkeypatch):
    data = pd.concat(
        [frame(symbol, ["2026-10-19", "2026-10-20"]) for symbol in cross_market.COMMODITY_SYMBOLS],
        axis=1,
    )
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda *_a, **_kw: data))
    quotes = cross_market._fetch_commodities()
    assert {row["as_of_date"] for row in quotes.values()} == {"2026-10-20"}
