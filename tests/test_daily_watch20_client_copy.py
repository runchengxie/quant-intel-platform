from __future__ import annotations

import pytest

from a_share_daily.daily_watch20 import DailyWatch20ValidationError
from a_share_daily.daily_watch20_client_render import (
    CLIENT_METHOD_SUMMARY,
    validate_daily_watch20_client_copy,
)


@pytest.mark.parametrize(
    "hint",
    [
        "A4 / B16",
        "4 + 16",
        "A/B 两组",
        "A腿与B腿",
        "双组合选股",
        "sleeve allocation",
        "Guarded16",
        "两路选股拼接",
        "拼合选股池",
        "xgb_score 与 guard_score",
        "模型探索与约束观察",
    ],
)
def test_client_copy_rejects_internal_construction_hints(hint: str) -> None:
    with pytest.raises(DailyWatch20ValidationError, match="construction hint"):
        validate_daily_watch20_client_copy(f"今日20只重点关注：{hint}")


def test_client_copy_allows_stock_names_ending_in_a() -> None:
    text = "今日20只重点关注：000037.SZ 深南电A"

    assert validate_daily_watch20_client_copy(text) == text


@pytest.mark.parametrize(
    "claim",
    [
        "模型已加入盈利质量因子",
        "模型使用个股市场 beta",
        "模型使用个股的市场 β",
        "模型已加入基本面成长",
        "模型已加入基本面增长",
        "模型使用营收增长特征",
        "模型已上线波动率变化率",
        "模型已上线波动率的变化率",
    ],
)
def test_client_copy_rejects_unsupported_feature_claims(claim: str) -> None:
    with pytest.raises(DailyWatch20ValidationError, match="unsupported DailyWatch20 feature"):
        validate_daily_watch20_client_copy(claim)


def test_client_copy_allows_current_feature_summary() -> None:
    assert validate_daily_watch20_client_copy(CLIENT_METHOD_SUMMARY) == CLIENT_METHOD_SUMMARY
