from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from a_share_daily.weekly_basket_preflight import (
    WeeklyBasketPreflightError,
    run_weekly_basket_preflight,
)
from a_share_daily.weekly_client_basket import SourcePosition


def _positions() -> list[SourcePosition]:
    return [
        SourcePosition(
            symbol=f"000{i:03d}.SZ",
            name=f"股票{i}",
            source_strategy="cashflow" if i <= 6 else "microcap",
            source_product="fixture",
            signal_date="20260911",
            valid_until="20260917",
            rank=i if i <= 6 else i - 6,
            score=1.0 / i,
            selection_reason="fixture",
            artifact_path="/production/provider/selection.json",
            artifact_sha256="a" * 64,
            research_only=True,
            eligible_for_live=False,
        )
        for i in range(1, 11)
    ]


def _inputs(tmp_path):
    instruments = tmp_path / "instruments.parquet"
    market = tmp_path / "market.parquet"
    calendar = tmp_path / "calendar.parquet"
    symbols = [f"000{i:03d}.SZ" for i in range(1, 11)]
    pd.DataFrame(
        {
            "ts_code": symbols,
            "name": [f"股票{i}" for i in range(1, 11)],
            "list_status": "L",
            "list_date": "20100101",
            "delist_date": None,
        }
    ).to_parquet(instruments)
    pd.DataFrame(
        {
            "ts_code": symbols,
            "trade_date": "20260911",
            "amount": 30_000_000.0,
            "is_st": False,
            "is_suspended": False,
            "close": 10.0,
        }
    ).to_parquet(market)
    pd.DataFrame(
        {
            "cal_date": ["20260911", "20260914", "20260915"],
            "is_open": [1, 1, 1],
        }
    ).to_parquet(calendar)
    return instruments, market, calendar


def test_preflight_accepts_first_open_day_and_current_snapshot(tmp_path) -> None:
    instruments, market, calendar = _inputs(tmp_path)
    result = run_weekly_basket_preflight(
        _positions(),
        report_date="20260914",
        instruments_path=instruments,
        market_path=market,
        calendar_path=calendar,
        enforce_stable_paths=False,
    )
    assert result.report_week == "2026-W38"
    assert result.prior_session == "20260911"
    assert result.position_count == 10


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("not_first_open", "first open"),
        ("wrong_market", "SSE/SZSE"),
        ("st", "ST"),
        ("suspended", "suspended"),
        ("delisted", "listed"),
        ("missing_price", "price"),
        ("low_amount", "amount"),
        ("stale_market", "prior session"),
    ],
)
def test_preflight_fails_closed(tmp_path, mutation, message) -> None:
    instruments, market, calendar = _inputs(tmp_path)
    positions = _positions()
    report_date = "20260914"
    if mutation == "not_first_open":
        report_date = "20260915"
    elif mutation == "wrong_market":
        positions[0] = replace(positions[0], symbol="430001.BJ")
    elif mutation == "delisted":
        frame = pd.read_parquet(instruments)
        frame.loc[0, ["list_status", "delist_date"]] = ["D", "20260901"]
        frame.to_parquet(instruments)
    else:
        frame = pd.read_parquet(market)
        if mutation == "st":
            frame.loc[0, "is_st"] = True
        elif mutation == "suspended":
            frame.loc[0, "is_suspended"] = True
        elif mutation == "missing_price":
            frame.loc[0, "close"] = None
        elif mutation == "low_amount":
            frame.loc[0, "amount"] = 19_999_999
        elif mutation == "stale_market":
            frame["trade_date"] = "20260910"
        frame.to_parquet(market)

    with pytest.raises(WeeklyBasketPreflightError, match=message):
        run_weekly_basket_preflight(
            positions,
            report_date=report_date,
            instruments_path=instruments,
            market_path=market,
            calendar_path=calendar,
            enforce_stable_paths=False,
        )


def test_preflight_rejects_worktree_inputs(tmp_path) -> None:
    instruments, market, calendar = _inputs(tmp_path)
    worktree_path = tmp_path / ".worktrees" / "market.parquet"
    worktree_path.parent.mkdir()
    market.replace(worktree_path)
    with pytest.raises(WeeklyBasketPreflightError, match="stable production"):
        run_weekly_basket_preflight(
            _positions(),
            report_date="20260914",
            instruments_path=instruments,
            market_path=worktree_path,
            calendar_path=calendar,
        )
