"""Bounded recovery of transient missing Yahoo equity results, without network I/O."""

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from a_share_daily import cross_market, fallback_fetch


def quotes(values):
    frame = pd.DataFrame(values, index=pd.to_datetime(["2026-10-16", "2026-10-19"]))
    frame.columns = pd.MultiIndex.from_tuples([("Close", symbol) for symbol in frame])
    return frame


def install_download(monkeypatch, symbols, batch, retry):
    calls = []

    def download(tickers, **kwargs):
        calls.append((tickers, kwargs))
        if len(calls) == 1:
            return batch
        assert kwargs["threads"] is False
        assert kwargs["timeout"] == 10
        assert kwargs["period"] == "5d"
        return retry(tickers[0])

    monkeypatch.setattr(cross_market, "US_SYMBOLS", symbols)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    return calls


def test_successful_batch_does_not_retry(monkeypatch):
    calls = install_download(monkeypatch, ["SPY"], quotes({"SPY": [100, 102]}), None)
    result = cross_market._fetch_us_stocks()
    assert result["SPY"]["close"] == 102
    assert len(calls) == 1


def test_only_missing_symbol_retries_and_preserves_success_and_actual_date(monkeypatch):
    calls = install_download(
        monkeypatch,
        ["SPY", "QQQ"],
        quotes({"SPY": [100, 102], "QQQ": [float("nan"), float("nan")]}),
        lambda symbol: quotes({symbol: [200, 206]}),
    )
    result = cross_market._fetch_us_stocks()
    assert [call[0] for call in calls] == [["SPY", "QQQ"], ["QQQ"]]
    assert result["SPY"]["close"] == 102
    assert result["QQQ"]["close"] == 206
    assert result["QQQ"]["pct_chg"] == 3
    assert result["QQQ"]["as_of_date"] == "2026-10-19"


@pytest.mark.parametrize("raises", [False, True])
def test_failed_retry_keeps_error_and_partial_exit(monkeypatch, raises):
    def retry(symbol):
        if raises:
            raise TimeoutError("transient failure")
        return quotes({symbol: [float("nan"), float("nan")]})

    calls = install_download(monkeypatch, ["SPY"], quotes({"SPY": [100, float("nan")]}), retry)
    result = cross_market._fetch_us_stocks()
    assert result["SPY"] == {"error": "insufficient data"}
    assert "as_of_date" not in result["SPY"]
    assert len(calls) == 2
    data = cross_market._annotate_freshness({"date": "20261020", "us_stocks": result}, "20261020")
    assert data["errors"] == ["SPY: insufficient data"]
    monkeypatch.setattr(fallback_fetch, "run", lambda *args, **kwargs: data)
    monkeypatch.setattr(sys, "argv", ["fallback_fetch", "--date", "20261020"])
    assert fallback_fetch.main() == 1


def test_retry_budget_is_at_most_six_symbols(monkeypatch):
    symbols = [f"MISSING{i}" for i in range(8)]
    calls = install_download(
        monkeypatch,
        symbols,
        quotes({symbol: [float("nan"), float("nan")] for symbol in symbols}),
        lambda symbol: quotes({symbol: [100, 101]}),
    )
    result = cross_market._fetch_us_stocks()
    assert [call[0] for call in calls[1:]] == [[symbol] for symbol in symbols[:6]]
    assert all("close" in result[symbol] for symbol in symbols[:6])
    assert all("error" in result[symbol] for symbol in symbols[6:])
