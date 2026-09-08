from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from a_share_daily import cross_market
from a_share_daily.cross_market import generate_summary
from a_share_daily.global_leadlag import aggregate_concept_signals


def test_aggregate_concept_signals_uses_instrument_weights() -> None:
    signals = aggregate_concept_signals(
        {
            "8035.T": {"pct_chg": 2.0},
            "6857.T": {"pct_chg": -1.0},
        }
    )

    equipment = next(item for item in signals if item["concept"] == "半导体设备")

    assert equipment["avg_pct_chg"] == 0.64
    assert equipment["markets"] == ["JP"]
    assert equipment["total_weight"] == 2.2


def test_generate_summary_prefers_global_lead_lag_mapping() -> None:
    summary = generate_summary(
        {
            "global_lead_lag": [
                {
                    "concept": "存储芯片",
                    "avg_pct_chg": 2.3,
                    "signal": "bullish",
                    "drivers": ["000660.KS +3.0%"],
                    "markets": ["KR"],
                }
            ],
            "concept_mapping": [],
        }
    )

    assert "### 全球领先资产映射" in summary
    assert "存储芯片（+2.3%） [KR]，驱动 000660.KS +3.0%" in summary


def test_fetch_cboe_uses_fred_vix(monkeypatch) -> None:
    monkeypatch.setattr(
        cross_market,
        "_fred_csv",
        lambda series_id: (18.0, 20.0, "2026-06-29"),
    )

    result = cross_market._fetch_cboe()

    assert result == {
        "as_of_date": "2026-06-29",
        "vix": 18.0,
        "vix_pct_chg": -10.0,
        "source": "fred_vixcls",
    }


def test_fred_csv_uses_shared_fred_fetcher() -> None:
    observed: dict[str, object] = {}

    class FakeFetcher:
        def fetch_observations(self, series_id: str, **kwargs: object) -> list[object]:
            observed.update(series_id=series_id, **kwargs)
            return [
                SimpleNamespace(date="2026-07-14", value=18.0),
                SimpleNamespace(date="2026-07-15", value=17.5),
            ]

    assert cross_market._fred_csv("VIXCLS", fetcher=FakeFetcher()) == (
        17.5,
        18.0,
        "2026-07-15",
    )
    assert observed == {
        "series_id": "VIXCLS",
        "start": "2026-01-01",
        "limit": 2,
        "timeout": cross_market.FRED_TIMEOUT,
    }


def test_fetch_cboe_does_not_fall_back_to_stale_csv(monkeypatch) -> None:
    def fail_fred(series_id: str) -> tuple[float, float, str]:
        raise RuntimeError(f"{series_id} unavailable")

    monkeypatch.setattr(cross_market, "_fred_csv", fail_fred)

    assert cross_market._fetch_cboe() is None


def test_cboe_history_csv_parses_latest_close(monkeypatch) -> None:
    class FakeResponse:
        text = "DATE,VVIX\n06/29/2026,84.500000\n06/30/2026,86.870000\n07/01/2026,89.040000\n"

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, timeout: int) -> FakeResponse:
        assert url.endswith("/VVIX_History.csv")
        assert timeout == cross_market.CBOE_TIMEOUT
        return FakeResponse()

    monkeypatch.setattr(cross_market.requests, "get", fake_get)

    assert cross_market._cboe_history_csv("VVIX_History.csv", "VVIX") == (
        89.04,
        86.87,
        "2026-07-01",
    )


def test_exact_snapshot_with_mismatched_payload_date_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    snapshot_root = tmp_path / "data-snapshots"
    snapshot_dir = snapshot_root / "cross-market"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "2026-06-30.json").write_text(
        json.dumps({"date": "20260629", "us_stocks": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cross_market, "_DATA_SNAPSHOTS_ROOT", snapshot_root)

    assert cross_market._load_snapshot("20260630") is None


def test_weekday_latest_snapshot_two_days_old_is_rejected(tmp_path: Path, monkeypatch) -> None:
    snapshot_root = tmp_path / "data-snapshots"
    latest_dir = snapshot_root / "latest"
    latest_dir.mkdir(parents=True)
    (latest_dir / "cross_market_snapshot.json").write_text(
        json.dumps({"date": "20260629", "us_stocks": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cross_market, "_DATA_SNAPSHOTS_ROOT", snapshot_root)

    assert cross_market._load_snapshot("20260701") is None


def test_load_snapshot_annotates_stale_fred_macro(tmp_path: Path, monkeypatch) -> None:
    snapshot_root = tmp_path / "data-snapshots"
    snapshot_dir = snapshot_root / "cross-market"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "2026-06-30.json").write_text(
        json.dumps(
            {
                "date": "20260630",
                "us_stocks": {},
                "macros": {
                    "^VIX": {
                        "label": "VIX 恐慌指数",
                        "close": 18.9,
                        "pct_chg": 1.4,
                        "as_of_date": "2026-06-25",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cross_market, "_DATA_SNAPSHOTS_ROOT", snapshot_root)

    snapshot = cross_market._load_snapshot("20260630")

    assert snapshot is not None
    assert snapshot["macros"]["^VIX"]["stale_days"] == 5
    assert "VIX 恐慌指数 快照日期为 2026-06-25，滞后 5 天" in snapshot["_freshness_warnings"]
