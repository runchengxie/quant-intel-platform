from __future__ import annotations

import json

import pytest

from a_share_daily.weekly_basket_state import (
    WeeklyBasketStateError,
    acquire_weekly_lock,
    load_previous_successful_basket,
)


def _basket(report_date: str = "20260914", symbol: str = "000001.SZ") -> dict:
    return {
        "schema_version": "a_share_daily.weekly_client_basket.v1",
        "report_date": report_date,
        "positions": [{"symbol": symbol}],
    }


def test_weekly_lock_reuses_frozen_basket_when_inputs_change(tmp_path) -> None:
    first = acquire_weekly_lock(
        tmp_path,
        report_week="2026-W38",
        target_hash="target123",
        basket=_basket(),
        input_hashes={"microcap": "a" * 64},
    )
    same = acquire_weekly_lock(
        tmp_path,
        report_week="2026-W38",
        target_hash="target123",
        basket=_basket(symbol="000002.SZ"),
        input_hashes={"microcap": "b" * 64},
    )
    assert same.path == first.path
    assert same.basket == first.basket
    assert same.basket["positions"][0]["symbol"] == "000001.SZ"
    assert same.revision == 1


def test_weekly_lock_override_requires_reason_and_increments_revision(tmp_path) -> None:
    acquire_weekly_lock(
        tmp_path,
        report_week="2026-W38",
        target_hash="target123",
        basket=_basket(),
        input_hashes={},
    )
    with pytest.raises(WeeklyBasketStateError, match="reason"):
        acquire_weekly_lock(
            tmp_path,
            report_week="2026-W38",
            target_hash="target123",
            basket=_basket(symbol="000002.SZ"),
            input_hashes={},
            override=True,
        )
    revised = acquire_weekly_lock(
        tmp_path,
        report_week="2026-W38",
        target_hash="target123",
        basket=_basket(symbol="000002.SZ"),
        input_hashes={},
        override=True,
        override_reason="correct bad upstream snapshot",
    )
    assert revised.revision == 2
    assert revised.basket["positions"][0]["symbol"] == "000002.SZ"


def test_weekly_lock_detects_tampering_and_finds_previous_success(tmp_path) -> None:
    first = acquire_weekly_lock(
        tmp_path,
        report_week="2026-W37",
        target_hash="target123",
        basket=_basket(report_date="20260907"),
        input_hashes={},
    )
    assert (
        load_previous_successful_basket(tmp_path, report_week="2026-W38", target_hash="target123")
        == first.basket
    )
    payload = json.loads(first.path.read_text())
    payload["basket"]["positions"][0]["symbol"] = "tampered"
    first.path.write_text(json.dumps(payload))
    with pytest.raises(WeeklyBasketStateError, match="tampered"):
        acquire_weekly_lock(
            tmp_path,
            report_week="2026-W37",
            target_hash="target123",
            basket=_basket(report_date="20260907"),
            input_hashes={},
        )
