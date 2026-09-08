"""Compact valid-policy fixture for DailyWatch20 consumer contract tests."""

from __future__ import annotations

import hashlib
import json
from typing import cast


def _model_policy() -> dict[str, object]:
    training: dict[str, object] = {
        "train_window_dates": 504,
        "sample_weight_mode": "exp_decay",
        "sample_weight_params": {"halflife": 126.0, "min_weight": 0.05},
        "min_query_size": 2,
    }
    training_id = hashlib.sha256(
        json.dumps(training, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "name": "DailyWatch20-XGB4-Guarded16-v2",
        "type": "xgb_ranker",
        "params": {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "max_depth": 3,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 2.0,
            "objective": "rank:pairwise",
            "tree_method": "hist",
            "random_state": 42,
        },
        "training_policy_id": training_id,
        "training_policy": training,
        "history_calendar_days": 1100,
        "retrain_weekdays": [0, 3],
        "max_model_age_trade_days": 5,
    }


def _features_and_label() -> tuple[dict[str, object], dict[str, object]]:
    feature_policy_id = (
        "daily_watch20.close_features.v1:"
        "minute_transform=daily_watch20.minute_features.close_open.v3:"
        "minute_lag_trade_days=0"
    )
    label_policy_id = "next_open_unsuspended_open_limit_aware.v3"
    feature_set_payload = {
        "features": ["trend_score"],
        "feature_policy_id": feature_policy_id,
        "label": "forward_rank_5d",
        "forward_days": 5,
        "label_horizon_weights": [[5, 1.0]],
        "label_policy_id": label_policy_id,
    }
    feature_set_id = hashlib.sha256(
        json.dumps(feature_set_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    features: dict[str, object] = {
        "feature_timing_schema": "daily_watch20.close_features.v1",
        "feature_policy_id": feature_policy_id,
        "feature_set_id": feature_set_id,
        "ordered_model_features": ["trend_score"],
        "available_features": ["trend_score"],
        "minute_feature_schema": "daily_watch20.minute_features.v3",
        "minute_source_contract": "canonical_minute_1m.hive.v1",
        "minute_transform_contract": "daily_watch20.minute_features.close_open.v3",
        "forward_days": 5,
        "minute_lag_trade_days": 0,
        "min_listed_days": 60,
        "liquidity_floor_quantile": 0.2,
        "date_col": "trade_date",
        "symbol_col": "symbol",
        "price_col": "adj_open",
    }
    label: dict[str, object] = {
        "policy_id": label_policy_id,
        "forward_days": 5,
        "horizon_weights": [{"trade_days": 5, "weight": 1.0}],
        "label_col": "forward_rank_5d",
        "forward_return_col": "forward_return_5d",
        "label_end_col": "forward_label_end_date",
        "feature_time": "source close",
        "entry_time": "next trade day open",
        "entry_tradability": "not suspended and not limit-up",
        "exit_tradability": "not suspended and not limit-down",
    }
    return features, label


def _construction() -> dict[str, object]:
    return {
        "schema_version": "daily_watch20.a4_b16_guarded.v1",
        "date_col": "trade_date",
        "symbol_col": "symbol",
        "industry_col": "first_industry_name",
        "ml_score_col": "xgb_score",
        "hard_eligibility_col": "hard_eligible",
        "guard_factors": [{"column": "trend_score", "weight": 1.0, "higher_is_better": True}],
        "ml_weight": 0.6,
        "guard_weight": 0.4,
        "industry_cap": 4,
        "b_retention_buffer": 8,
        "b_max_replacements": 4,
        "a_tracking_weight": 0.2,
        "fallback_mode": "none",
        "sleeves": {"A": 4, "B": 16},
    }


def build_valid_v2_policy(receipt: dict[str, object]) -> dict[str, object]:
    """Return the smallest policy accepted by the producer's canonical semantics."""

    candidate_pool = cast(dict[str, object], receipt["candidate_pool"])
    features, label = _features_and_label()
    return {
        "schema_version": "daily_watch20.strategy_policy.v1",
        "model": _model_policy(),
        "features": features,
        "label": label,
        "candidate_pool": {
            "mode": candidate_pool["mode"],
            "policy_id": candidate_pool["policy_id"],
            "restricted": True,
            "fail_closed": True,
            "positive_change_only": True,
            "min_symbols": candidate_pool["min_symbols"],
            "snapshot_min_symbols": candidate_pool["snapshot_min_symbols"],
            **(
                {"max_missing_ranks": candidate_pool["max_missing_ranks"]}
                if candidate_pool["mode"] in {"ths_hot_strict_v2", "ths_hot_strict_v3"}
                else {}
            ),
        },
        "news_heat": {
            "schema_version": "daily_watch20.news_heat.v1",
            "configured_enabled": False,
            "effective_enabled": False,
            "minimum_rows": 20,
            "coverage_mode": "sparse_positive_only",
            "missing_symbol_semantics": "neutral_unknown",
        },
        "construction": _construction(),
        "safety": {
            "market_scope": "sh-sz",
            "eligible_for_backtest": True,
            "eligible_for_live": False,
            "publication_tier": "production",
            "publication_timezone": "Asia/Shanghai",
            "publication_window_start": "00:00:00",
            "publication_window_end_exclusive": "09:15:00",
        },
    }


__all__ = ["build_valid_v2_policy"]
