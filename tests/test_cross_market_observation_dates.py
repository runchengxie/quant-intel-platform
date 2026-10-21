"""Historical recovery must not silently consume future or undated quotes."""

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from a_share_daily import cross_market, fallback_fetch


def quotes(symbols, dates):
    return pd.DataFrame(
        {("Close", symbol): range(100, 100 + len(dates)) for symbol in symbols},
        index=pd.DatetimeIndex(dates),
    )


@pytest.mark.parametrize("trade_date", ["20261020", "20261018"])
def test_commodities_select_requested_session_before_future_bar(monkeypatch, trade_date):
    dates = (
        ["2026-10-19", "2026-10-20", "2026-10-21"]
        if trade_date == "20261020"
        else ["2026-10-15", "2026-10-16", "2026-10-19"]
    )
    data = quotes(cross_market.COMMODITY_SYMBOLS, dates)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda *_a, **_kw: data))
    result = cross_market._fetch_commodities(trade_date)
    assert {row["as_of_date"] for row in result.values()} == {dates[1]}
    assert {row["close"] for row in result.values()} == {101.0}


def test_dxy_selects_requested_session(monkeypatch):
    data = quotes(cross_market._DXY_SYMBOLS, ["2026-10-19", "2026-10-20", "2026-10-21"])
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda *_a, **_kw: data))
    monkeypatch.setattr(cross_market, "_fred_csv", lambda *_a: (1, 1, "2026-10-20"))
    monkeypatch.setattr(cross_market, "_cboe_history_csv", lambda *_a: (1, 1, "2026-10-20"))
    row = cross_market._fetch_macros("20261020")["DX-Y.NYB"]
    assert row["close"] == 101
    assert row["as_of_date"] == "2026-10-20"


def test_etf_missing_target_is_an_error(monkeypatch):
    data = quotes(cross_market.COMMODITY_SYMBOLS, ["2026-10-16", "2026-10-19", "2026-10-21"])
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda *_a, **_kw: data))
    result = cross_market._fetch_commodities("20261020")
    assert {result[symbol]["error"] for symbol in ["SLV", "GLD"]} == {"missing target session"}
    assert result["GC=F"]["as_of_date"] == "2026-10-19"


@pytest.mark.parametrize(
    "section,symbol",
    [("us_stocks", "TSLA"), ("commodities", "GLD"), ("macros", "DX-Y.NYB"), ("macros", "^TNX")],
)
@pytest.mark.parametrize("observed", ["2026-10-21", None, "bad-date"])
def test_invalid_or_future_quote_dates_fail_closed(monkeypatch, section, symbol, observed):
    data = cross_market._annotate_freshness(
        {"date": "20261020", section: {symbol: {"close": 1, "as_of_date": observed}}}, "20261020"
    )
    assert data["_freshness_warnings"]
    monkeypatch.setattr(fallback_fetch, "run", lambda *_a, **_kw: data)
    monkeypatch.setattr(sys, "argv", ["fallback_fetch", "--date", "20261020"])
    assert fallback_fetch.main() == 1


@pytest.mark.parametrize("observed", ["2026-10-21", None, "bad-date"])
def test_invalid_or_future_cboe_date_warns(observed):
    result = cross_market._annotate_freshness(
        {"date": "20261020", "cboe_putcall": {"vix": 1, "as_of_date": observed}}, "20261020"
    )
    assert result["_freshness_warnings"]


def test_dxy_insufficient_bounded_data_is_an_error(monkeypatch):
    data = quotes(cross_market._DXY_SYMBOLS, ["2026-10-19", "2026-10-21"])
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda *_a, **_kw: data))
    monkeypatch.setattr(cross_market, "_fred_csv", lambda *_a: (1, 1, "2026-10-20"))
    monkeypatch.setattr(cross_market, "_cboe_history_csv", lambda *_a: (1, 1, "2026-10-20"))
    assert cross_market._fetch_macros("20261020")["DX-Y.NYB"]["error"] == "insufficient data"


def test_undated_commodity_compatibility_keeps_latest_mode(monkeypatch):
    data = quotes(cross_market.COMMODITY_SYMBOLS, ["2026-10-19", "2026-10-20", "2026-10-21"])
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda *_a, **_kw: data))
    assert {row["as_of_date"] for row in cross_market._fetch_commodities().values()} == {
        "2026-10-21"
    }


def test_existing_macro_lag_boundary_is_preserved():
    recent = cross_market._annotate_freshness(
        {"date": "20261020", "macros": {"^TNX": {"close": 1, "as_of_date": "2026-10-19"}}},
        "20261020",
    )
    assert not recent.get("_freshness_warnings")
    stale = cross_market._annotate_freshness(
        {"date": "20261020", "macros": {"^TNX": {"close": 1, "as_of_date": "2026-10-15"}}},
        "20261020",
    )
    assert stale["_freshness_warnings"]


def test_failed_dxy_response_reaches_partial_exit(monkeypatch):
    data = cross_market._annotate_freshness(
        {"date": "20261020", "macros": {"DX-Y.NYB": {"error": "missing target session"}}},
        "20261020",
    )
    assert "DX-Y.NYB: missing target session" in data["errors"]
    monkeypatch.setattr(fallback_fetch, "run", lambda *_a, **_kw: data)
    monkeypatch.setattr(sys, "argv", ["fallback_fetch", "--date", "20261020"])
    assert fallback_fetch.main() == 1


def test_futures_and_fx_keep_real_bars_on_nyse_holiday(monkeypatch):
    symbols = [*cross_market.COMMODITY_SYMBOLS, *cross_market._DXY_SYMBOLS]
    data = quotes(symbols, ["2026-12-23", "2026-12-24", "2026-12-25", "2026-12-28"])
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda *_a, **_kw: data))
    monkeypatch.setattr(cross_market, "_fred_csv", lambda *_a: (1, 1, "2026-12-24"))
    monkeypatch.setattr(cross_market, "_cboe_history_csv", lambda *_a: (1, 1, "2026-12-24"))
    commodities = cross_market._fetch_commodities("20261225")
    assert commodities["GC=F"]["as_of_date"] == "2026-12-25"
    assert commodities["GLD"]["as_of_date"] == "2026-12-24"
    assert commodities["SLV"]["as_of_date"] == "2026-12-24"
    assert cross_market._fetch_macros("20261225")["DX-Y.NYB"]["as_of_date"] == "2026-12-25"


@pytest.mark.parametrize("symbol", ["GC=F", "DX-Y.NYB"])
def test_non_exchange_quotes_reject_duplicate_session_dates(symbol):
    data = quotes([symbol], ["2026-10-19", "2026-10-20", "2026-10-20"])
    assert (
        cross_market._bounded_daily_quote(data, symbol, "20261020")["error"]
        == "duplicate session data"
    )


@pytest.mark.parametrize("symbol", ["GC=F", "DX-Y.NYB"])
def test_non_exchange_quotes_reject_missing_date_index(symbol):
    data = pd.DataFrame({("Close", symbol): [100, 101]})
    assert cross_market._bounded_daily_quote(data, symbol, "20261020")["error"] == "no dated data"
