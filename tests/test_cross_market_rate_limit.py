from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from a_share_daily import cross_market
from a_share_daily.cross_market_rate_limit import next_retry_at


def test_cooldown_is_bounded_and_honors_retry_after():
    now = datetime(2026, 10, 22, tzinfo=UTC)
    assert next_retry_at(now, 1, None) == now + timedelta(minutes=15)
    assert next_retry_at(now, 99, None) == now + timedelta(minutes=60)
    assert next_retry_at(now, 1, "120") == now + timedelta(seconds=120)
    assert next_retry_at(now, 1, "Thu, 22 Oct 2026 00:02:00 GMT") == now + timedelta(seconds=120)
    assert next_retry_at(now, 1, "nonsense") == now + timedelta(minutes=15)


def test_typed_rate_limit_stops_serial_retries(monkeypatch):
    import sys

    class YFRateLimitError(Exception):
        pass

    monkeypatch.setenv("CROSS_MARKET_YAHOO_COOLDOWN_UNTIL", "")
    calls = []

    class Ticker:
        def __init__(self, symbol):
            calls.append(symbol)

        def history(self, **kwargs):
            raise YFRateLimitError("rate limited")

    frame = pd.DataFrame(
        {("Close", "SPY"): [float("nan")] * 2, ("Close", "QQQ"): [float("nan")] * 2},
        index=pd.to_datetime(["2026-10-20", "2026-10-21"]),
    )
    monkeypatch.setattr(cross_market, "US_SYMBOLS", ["SPY", "QQQ"])
    monkeypatch.setitem(
        sys.modules, "yfinance", SimpleNamespace(Ticker=Ticker, download=lambda *a, **k: frame)
    )
    result = cross_market._fetch_us_stocks()
    assert calls == ["SPY"]
    assert result["SPY"]["rate_limited"] is True


def test_active_cooldown_does_not_call_yahoo(monkeypatch):
    import sys

    monkeypatch.setenv(
        "CROSS_MARKET_YAHOO_COOLDOWN_UNTIL", (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
    )
    monkeypatch.setitem(
        sys.modules, "yfinance", SimpleNamespace(download=lambda *a, **k: pytest.fail("network"))
    )
    result = cross_market._fetch_us_stocks()
    assert all(v["error"] == "yahoo cooldown" for v in result.values())
