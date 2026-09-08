from __future__ import annotations

import pandas as pd

from a_share_daily.topic_summary_fallback import build_fallback_topic_summary


def test_dc_concept_topic_summary_aggregates_concepts_without_degradation() -> None:
    concept = pd.DataFrame(
        [
            {"theme_code": "A", "name": "人工智能", "pct_change": 5.0, "main_change": 100.0, "z_t_num": 2},
            {"theme_code": "B", "name": "新能源", "pct_change": 1.0, "main_change": 10.0, "z_t_num": 0},
        ]
    )
    members = pd.DataFrame(
        [
            {"theme_code": "A", "ts_code": "000001.SZ"},
            {"theme_code": "A", "ts_code": "000002.SZ"},
            {"theme_code": "B", "ts_code": "000003.SZ"},
        ]
    )
    limits = pd.DataFrame([{"ts_code": "000001.SZ", "limit_type": "涨停池"}])
    moneyflow = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "net_amount": 20.0},
            {"ts_code": "000002.SZ", "net_amount": 10.0},
        ]
    )
    daily = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "pct_chg": 5.0},
            {"ts_code": "000002.SZ", "pct_chg": 2.0},
            {"ts_code": "000003.SZ", "pct_chg": -1.0},
        ]
    )

    result = build_fallback_topic_summary(
        "20260831",
        concept=concept,
        members=members,
        limits=limits,
        moneyflow=moneyflow,
        daily=daily,
    )

    assert result["source"] == "hotspot_composite_v1"
    assert result["degraded"] is False
    assert result["topics"][0]["topic"] == "人工智能"
    assert result["topics"][0]["count"] == 2
    assert result["topics"][0]["limit_up_count"] == 1
    assert result["topics"][0]["moneyflow_net_amount"] == 30.0
    assert result["source_status"]["daily"] == "passed"
    assert result["degraded"] is False
