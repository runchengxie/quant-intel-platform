"""A date-current partial snapshot must not freeze provider recovery."""

import sys
from pathlib import Path

import pytest

from a_share_daily import cross_market, fallback_fetch

TRADE_DATE = "20261020"


def install_live(monkeypatch, layer, equities):
    calls = []
    monkeypatch.delenv("CROSS_MARKET_FORCE_LIVE", raising=False)

    def fetch(_trade_date=None):
        calls.append("live")
        return equities

    if layer == "fallback":

        def live_run(_date):
            rows = fetch()
            return cross_market._annotate_freshness(
                {"date": TRADE_DATE, "us_stocks": rows}, TRADE_DATE
            )

        monkeypatch.setattr(cross_market, "run", live_run)
        monkeypatch.setattr(fallback_fetch, "_write_snapshot", lambda *_args: Path("mock.json"))
        run = fallback_fetch.run
    else:
        monkeypatch.setattr(cross_market, "_fetch_us_stocks", fetch)
        monkeypatch.setattr(cross_market, "_fetch_aaii", lambda: None)
        monkeypatch.setattr(cross_market, "_fetch_cboe_into", lambda _result: None)
        monkeypatch.setattr(cross_market, "_map_us_into", lambda _result: None)
        monkeypatch.setattr(cross_market, "_map_commodities_into", lambda _result: None)
        monkeypatch.setattr(cross_market, "_fetch_commodities", lambda _date=None: {})
        monkeypatch.setattr(cross_market, "_fetch_macros", lambda _date=None: {})
        monkeypatch.setattr(cross_market, "_fetch_korea_signals", lambda _date: ({}, {}, {}))
        run = cross_market.run
    return run, calls


@pytest.mark.parametrize("layer", ["fallback", "core"])
def test_partial_snapshot_without_freshness_warning_invokes_live(monkeypatch, layer):
    snapshot = {"date": TRADE_DATE, "errors": ["QQQ: insufficient data"], "_freshness_warnings": []}
    monkeypatch.setattr(cross_market, "_load_snapshot", lambda _date: snapshot)
    run, calls = install_live(
        monkeypatch, layer, {"QQQ": {"close": 102, "pct_chg": 2, "as_of_date": "2026-10-20"}}
    )
    result = run(TRADE_DATE)
    assert calls == ["live"]
    assert result["errors"] == []
    assert result["us_stocks"]["QQQ"]["as_of_date"] == "2026-10-20"


@pytest.mark.parametrize("layer", ["fallback", "core"])
def test_complete_snapshot_does_not_invoke_live(monkeypatch, layer):
    snapshot = {"date": TRADE_DATE, "errors": [], "_freshness_warnings": []}
    monkeypatch.setattr(cross_market, "_load_snapshot", lambda _date: snapshot)
    run, calls = install_live(monkeypatch, layer, {})
    assert run(TRADE_DATE) is snapshot
    assert calls == []


@pytest.mark.parametrize("layer", ["fallback", "core"])
def test_failed_live_recovery_keeps_errors_and_partial_exit(monkeypatch, layer):
    snapshot = {"date": TRADE_DATE, "errors": ["QQQ: insufficient data"], "_freshness_warnings": []}
    monkeypatch.setattr(cross_market, "_load_snapshot", lambda _date: snapshot)
    run, calls = install_live(monkeypatch, layer, {"QQQ": {"error": "insufficient data"}})
    result = run(TRADE_DATE)
    assert calls == ["live"]
    assert result["errors"] == ["QQQ: insufficient data"]
    assert "as_of_date" not in result["us_stocks"]["QQQ"]
    monkeypatch.setattr(fallback_fetch, "run", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(sys, "argv", ["fallback_fetch", "--date", TRADE_DATE])
    assert fallback_fetch.main() == 1


def test_freshness_only_failure_reaches_partial_exit(monkeypatch):
    data = {"date": TRADE_DATE, "errors": [], "_freshness_warnings": ["stale macro"]}
    monkeypatch.setattr(fallback_fetch, "run", lambda *_args, **_kwargs: data)
    monkeypatch.setattr(sys, "argv", ["fallback_fetch", "--date", TRADE_DATE])
    assert fallback_fetch.main() == 1
