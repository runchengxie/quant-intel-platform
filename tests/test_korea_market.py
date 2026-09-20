from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from a_share_daily import cross_market
from a_share_daily.korea_market import (
    compute_korea_signal,
    fetch_korea_daily_quotes,
)


def test_fetch_korea_daily_quotes_uses_finance_datareader_without_api_key() -> None:
    calls: list[tuple[str, str, str]] = []

    class FakeFdr:
        @staticmethod
        def DataReader(symbol: str, start: str, end: str) -> pd.DataFrame:
            calls.append((symbol, start, end))
            return pd.DataFrame({"Close": [100.0, 105.0]})

    result = fetch_korea_daily_quotes(
        ["005930.KS"],
        "2026-09-10",
        "2026-09-14",
        fdr_module=FakeFdr,
        pykrx_module=None,
        yfinance_module=None,
    )

    assert calls == [("005930.KS", "2026-09-10", "2026-09-14")]
    assert result["005930.KS"] == {
        "close": 105.0,
        "pct_chg": 5.0,
        "source": "finance-datareader",
        "degraded": True,
    }


def test_fetch_korea_daily_quotes_falls_back_to_pykrx_when_fdr_fails() -> None:
    class BrokenFdr:
        @staticmethod
        def DataReader(*args: object, **kwargs: object) -> pd.DataFrame:
            raise RuntimeError("fdr unavailable")

    class FakeStock:
        @staticmethod
        def get_market_ohlcv(start: str, end: str, ticker: str) -> pd.DataFrame:
            assert start == "20260910"
            assert end == "20260914"
            return pd.DataFrame({"종가": [200.0, 190.0]})

    result = fetch_korea_daily_quotes(
        ["005930.KS"],
        "2026-09-10",
        "2026-09-14",
        fdr_module=BrokenFdr,
        pykrx_module=SimpleNamespace(stock=FakeStock),
        yfinance_module=None,
    )

    assert result["005930.KS"]["source"] == "pykrx"
    assert result["005930.KS"]["pct_chg"] == -5.0


def test_compute_korea_signal_returns_concept_and_risk_level() -> None:
    signal = compute_korea_signal(
        {
            "005930.KS": {"pct_chg": 4.0},
            "000660.KS": {"pct_chg": 6.0},
            "042700.KS": {"pct_chg": 2.0},
            "^KS11": {"pct_chg": 0.5},
        },
        window="preopen",
    )

    assert signal["window"] == "preopen"
    assert signal["signal"] == "bullish"
    assert signal["risk_level"] == "high"
    assert signal["source"] == "daily-proxy"
    assert "HBM" in signal["concepts"]


def test_render_korea_signal_is_optional_and_honest_about_proxy() -> None:
    text = cross_market.generate_summary(
        {
            "korea_preopen": {
                "window": "preopen",
                "signal": "bullish",
                "risk_level": "high",
                "avg_pct_chg": 3.2,
                "concepts": ["HBM", "存储芯片"],
                "source": "daily-proxy",
            }
        }
    )

    assert "### 韩国早盘 → A股开盘信号" in text
    assert "日线代理" in text
    assert "HBM、存储芯片" in text


def test_run_includes_korea_signal_fields_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(cross_market, "_load_snapshot", lambda _date: None)
    monkeypatch.setattr(cross_market, "_fetch_us_stocks", lambda: {})
    monkeypatch.setattr(cross_market, "_fetch_aaii", lambda: None)
    monkeypatch.setattr(cross_market, "_fetch_cboe", lambda: None)
    monkeypatch.setattr(cross_market, "_fetch_commodities", lambda: {})
    monkeypatch.setattr(cross_market, "_fetch_macros", lambda: {})
    monkeypatch.setattr(
        cross_market,
        "_fetch_korea_signals",
        lambda _date: (
            {"005930.KS": {"pct_chg": 1.0}},
            {"signal": "neutral", "source": "daily-proxy"},
            {"signal": "neutral", "source": "daily-proxy"},
        ),
    )

    result = cross_market.run("20260914")

    assert result["korea_preopen"]["source"] == "daily-proxy"
    assert result["korea_overnight"]["signal"] == "neutral"
