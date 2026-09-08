from __future__ import annotations

import pytest

from a_share_daily.market_temperature import (
    build_market_temperature,
    evaluate_conditions,
)


def _july_15_inputs() -> dict:
    return {
        "overview": {
            "turnover_total": 1_520_000_000_000,
            "breadth": {"up": 1_500, "down": 3_600, "flat": 100, "total": 5_200},
            "median_pct_chg": -0.89,
            "vwap_above_ratio": 31.0,
            "up5_count": 185,
            "down5_count": 260,
            # The pure calculation must ignore this legacy approximation.
            "down_limit_approx": 56,
        },
        "indices": {
            "000001.SH": {
                "pct_chg": 0.42,
                "close": 3500,
                "pre_close": 3485,
                "high": 3510,
                "low": 3470,
            },
            "399001.SZ": {
                "pct_chg": 0.31,
                "close": 11000,
                "pre_close": 10966,
                "high": 11020,
                "low": 10920,
            },
            "399006.SZ": {
                "pct_chg": 0.18,
                "close": 2200,
                "pre_close": 2196,
                "high": 2210,
                "low": 2180,
            },
            "000300.SH": {
                "pct_chg": 0.27,
                "close": 4100,
                "pre_close": 4089,
                "high": 4110,
                "low": 4060,
            },
        },
        "limits": {
            "limit_up": {"count": 74},
            "limit_down": {"count": 39},
            "failed_board_count": 20,
        },
        "moneyflow": {
            "moneyflow": {
                "net_in": 100.0,
                "net_out": -70.0,
                "inflow_stocks": 2_900,
                "outflow_stocks": 2_200,
            }
        },
        "industries": [
            *[{"avg_pct_chg": 0.8} for _ in range(24)],
            *[{"avg_pct_chg": -0.4} for _ in range(8)],
        ],
        "turnover_history": [
            1_000_000_000_000,
            1_080_000_000_000,
            1_100_000_000_000,
            1_120_000_000_000,
            1_150_000_000_000,
            1_180_000_000_000,
            1_200_000_000_000,
            1_230_000_000_000,
        ],
    }


def test_july_15_structure_surfaces_heat_breadth_contradiction() -> None:
    result = build_market_temperature("20260715", **_july_15_inputs())

    assert result["calibration"] == "provisional_observation_scale"
    assert result["position_mapping"] is None
    assert set(result["dimensions"]) == {
        "liquidity",
        "breadth",
        "profit_effect",
        "loss_risk",
        "trend_confirmation",
        "rotation_quality",
    }
    assert result["metrics"]["breadth_up_ratio"] == pytest.approx(1_500 / 5_200, abs=1e-4)
    # Exact limit bands win: the legacy approximation of 56 is never consumed.
    assert result["metrics"]["limit_down_ratio"] == pytest.approx(39 / 5_200, abs=1e-4)
    assert result["dimensions"]["profit_effect"]["score"] > result["dimensions"]["breadth"]["score"]
    tension_ids = {item["id"] for item in result["core_tensions"]}
    assert "hotspots_vs_breadth" in tension_ids
    assert "indices_vs_stock_breadth" in tension_ids
    assert result["validation_conditions"][0]["id"] == "breadth_repair"
    assert 0 < result["confidence"] <= 1
    assert result["heat_score"] is not None
    assert result["fragility_score"] is not None
    assert "成交额相对基线仅有 8 个历史交易日" in result["data_warnings"]


def test_missing_inputs_do_not_turn_into_zero_scores() -> None:
    result = build_market_temperature(
        "20260715",
        overview={},
        indices={},
        limits={},
        moneyflow={},
        industries=[],
        turnover_history=[],
    )

    assert result["heat_score"] is None
    assert result["fragility_score"] is None
    assert result["status_label"] == "数据不足"
    assert result["confidence"] == 0
    assert all(item["score"] is None for item in result["dimensions"].values())
    assert result["validation_conditions"] == []

    partial = build_market_temperature(
        "20260715",
        overview={"median_pct_chg": -0.5},
        indices={},
        limits={"seal_rate": 0.8, "failed_board_ratio": 0.2},
        moneyflow={},
        industries=[],
        turnover_history=[],
    )
    assert partial["dimensions"]["breadth"]["score"] is None
    assert partial["dimensions"]["profit_effect"]["score"] is None
    assert partial["confidence"] < 0.35


def test_broad_stock_repair_without_index_confirmation_is_explicit() -> None:
    inputs = _july_15_inputs()
    inputs["overview"].update(
        {
            "breadth": {"up": 3_151, "down": 1_974, "flat": 75, "total": 5_200},
            "median_pct_chg": 0.77,
            "wavg_pct_chg": -1.67,
            "vwap_above_ratio": 45.7,
            "up5_count": 294,
            "down5_count": 450,
        }
    )
    for index in inputs["indices"].values():
        index["pct_chg"] = -1.0
        index["close"] = index["low"]
    inputs["limits"].pop("failed_board_count")

    result = build_market_temperature("20260715", **inputs)

    tension_ids = {item["id"] for item in result["core_tensions"]}
    assert "stock_breadth_vs_indices" in tension_ids
    assert "stock_median_vs_turnover_weighted" in tension_ids
    assert "close_breadth_vs_vwap" in tension_ids
    assert result["metrics"]["turnover_weighted_return"] == pytest.approx(-0.0167)
    assert result["fragility_score"] >= 55
    assert "脆弱" in result["status_label"]
    validation_ids = {item["id"] for item in result["validation_conditions"]}
    assert {
        "index_participation_repair",
        "turnover_weighted_repair",
        "vwap_confirmation",
        "loss_tail_cooling",
    }.issubset(validation_ids)


def test_evaluate_conditions_and_previous_review_are_explicit() -> None:
    conditions = [
        {
            "id": "breadth_repair",
            "metric": "breadth_up_ratio",
            "operator": ">",
            "target": 0.30,
        },
        {
            "id": "loss_tail_cooling",
            "metric": "down5_ratio",
            "operator": "<",
            "target": 0.05,
        },
        {
            "id": "rotation_missing",
            "metric": "industry_positive_ratio",
            "operator": ">=",
            "target": 0.60,
        },
    ]
    evaluations = evaluate_conditions(
        conditions,
        {"breadth_up_ratio": 0.40, "down5_ratio": 0.06},
    )

    assert [item["status"] for item in evaluations] == [
        "confirmed",
        "invalidated",
        "not_evaluable",
    ]
    assert evaluations[2]["reason"] == "current_metric_missing"

    inputs = _july_15_inputs()
    result = build_market_temperature(
        "20260715",
        **inputs,
        previous={"validation_conditions": conditions},
    )
    statuses = {item["id"]: item["status"] for item in result["previous_validation"]}
    assert statuses["loss_tail_cooling"] == "invalidated"
    assert statuses["rotation_missing"] == "confirmed"
