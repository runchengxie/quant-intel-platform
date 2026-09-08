from __future__ import annotations

import json
from pathlib import Path

import pytest

from a_share_daily import cross_market, fallback_fetch


def test_summary_renders_counts_without_error() -> None:
    data = {
        "date": "20260629",
        "_source": "live",
        "us_stocks": {
            "SPY": {"close": 610.1},
            "QQQ": {"close": 540.2},
            "DIA": {},
        },
        "commodities": {"GC=F": {"close": 2300.0}},
        "macros": {"^VIX": {"close": 18.9}},
        "errors": ["boom"],
        "_freshness_warnings": ["stale"],
    }
    text = fallback_fetch._summary(data)

    assert "date=20260629" in text
    assert "us=2/3" in text
    assert "comm=1" in text
    assert "macro=1" in text
    assert "errors=1" in text
    assert "freshness_warnings=1" in text
    assert "[live]" in text


def test_summary_handles_missing_sections() -> None:
    text = fallback_fetch._summary({"date": "20260629"})

    assert "us=0/0" in text
    assert "errors=0" in text
    assert "freshness_warnings=0" in text


def test_write_snapshot_roundtrips(tmp_path: Path) -> None:
    data = {"date": "20260629", "us_stocks": {"SPY": {"close": 1.0}}}

    # Redirect the module-level snapshot dirs to tmp_path.
    snapshot_dir = tmp_path / "data-snapshots" / "cross-market"
    latest_dir = tmp_path / "data-snapshots" / "latest"
    fallback_fetch.SNAPSHOT_DIR = snapshot_dir
    fallback_fetch.LATEST_DIR = latest_dir

    path = fallback_fetch._write_snapshot(data, "20260629")

    assert path == snapshot_dir / "2026-06-29.json"
    assert path.exists()

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == data

    latest = latest_dir / "cross_market_snapshot.json"
    assert latest.exists()
    assert json.loads(latest.read_text(encoding="utf-8")) == data


def test_run_returns_snapshot_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = {
        "date": "20260629",
        "us_stocks": {"SPY": {"close": 1.0}},
        "_source": "snapshot",
    }

    def fake_load(trade_date: str) -> dict | None:
        assert trade_date == "20260629"
        return snapshot

    monkeypatch.setattr(cross_market, "_load_snapshot", fake_load)
    # live_run must NOT be called.
    called = {"value": False}

    def fake_live(_trade_date: str) -> dict:
        called["value"] = True
        return {}

    monkeypatch.setattr(cross_market, "run", fake_live)

    result = fallback_fetch.run("20260629")

    assert result == snapshot
    assert called["value"] is False


def test_run_does_not_accept_snapshot_for_a_different_requested_date(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stale = {
        "date": "20260825",
        "us_stocks": {"SPY": {"close": 1.0}},
        "_source": "snapshot",
    }
    fresh = {
        "date": "20260826",
        "us_stocks": {"SPY": {"close": 2.0}},
        "errors": [],
    }

    monkeypatch.setattr(cross_market, "_load_snapshot", lambda _date: stale)
    live_dates: list[str] = []

    def fake_live(date: str) -> dict:
        live_dates.append(date)
        return dict(fresh)

    monkeypatch.setattr(cross_market, "run", fake_live)
    fallback_fetch.SNAPSHOT_DIR = tmp_path / "data-snapshots" / "cross-market"
    fallback_fetch.LATEST_DIR = tmp_path / "data-snapshots" / "latest"

    result = fallback_fetch.run("20260826")

    assert result["date"] == "20260826"
    assert result["_source"] == "local-fallback"
    assert live_dates == ["20260826"]


def test_run_writes_back_after_live_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    live = {
        "date": "20260629",
        "us_stocks": {"SPY": {"close": 2.0}},
        "errors": [],
    }

    monkeypatch.setattr(cross_market, "_load_snapshot", lambda _t: None)
    monkeypatch.setattr(cross_market, "run", lambda _t: dict(live))

    snapshot_dir = tmp_path / "data-snapshots" / "cross-market"
    latest_dir = tmp_path / "data-snapshots" / "latest"
    fallback_fetch.SNAPSHOT_DIR = snapshot_dir
    fallback_fetch.LATEST_DIR = latest_dir

    result = fallback_fetch.run("20260629", force_live=True)

    assert result["_source"] == "local-fallback"
    assert (snapshot_dir / "2026-06-29.json").exists()
    written = json.loads((snapshot_dir / "2026-06-29.json").read_text(encoding="utf-8"))
    assert written["_source"] == "local-fallback"
    assert written["us_stocks"]["SPY"]["close"] == 2.0


def test_run_propagates_live_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cross_market, "_load_snapshot", lambda _t: None)
    monkeypatch.setattr(
        cross_market, "run", lambda _t: (_ for _ in ()).throw(RuntimeError("network down"))
    )

    with pytest.raises(RuntimeError, match="network down"):
        fallback_fetch.run("20260629")


def test_stale_snapshot_date_is_marked_before_fallback_accepts_it() -> None:
    data = cross_market._annotate_freshness(
        {"date": "20260628", "us_stocks": {}, "commodities": {}, "macros": {}},
        "20260629",
    )

    assert data["_freshness_warnings"] == [
        "cross-market snapshot date is 20260628, requested 20260629"
    ]
