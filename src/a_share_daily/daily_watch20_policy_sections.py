"""Producer-mirrored semantic validators for DailyWatch20 policy sections.

Kept local so the morning consumer has no runtime dependency on the producer
repository. The public facade and receipt-carrier checks live in
``daily_watch20_policy``.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, cast

_MODEL_NAME = "DailyWatch20-XGB4-Guarded16-v2"
_MODEL_TYPES = frozenset({"xgb_ranker"})
_FEATURE_TIMING_SCHEMA = "daily_watch20.close_features.v1"
_MINUTE_FEATURE_SCHEMA = "daily_watch20.minute_features.v3"
_MINUTE_SOURCE_CONTRACT = "canonical_minute_1m.hive.v1"
_MINUTE_TRANSFORM_CONTRACT = "daily_watch20.minute_features.close_open.v3"
_NEWS_HEAT_SCHEMA = "daily_watch20.news_heat.v1"
_CONSTRUCTION_SCHEMA = "daily_watch20.a4_b16_guarded.v1"
_CANDIDATE_MODES = frozenset(
    {"all_market", "ths_hot_strict", "ths_hot_strict_v2", "ths_hot_strict_v3"}
)
_ALL_MARKET_POLICY_ID = "daily_watch20.all_market.v1"
_THS_HOT_POLICY_SCHEMAS = {
    "ths_hot_strict": "daily_watch20.ths_hot_positive_close.v1",
    "ths_hot_strict_v2": "daily_watch20.ths_hot_positive_close.v2",
    "ths_hot_strict_v3": "daily_watch20.ths_hot_positive_close.v3",
}
_THS_HOT_V2_MAX_MISSING_RANKS = 2
_THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS = 100
_PUBLICATION_TIMEZONE = "Asia/Shanghai"
_PUBLICATION_WINDOW_START = "00:00:00"
_PUBLICATION_WINDOW_END = "09:15:00"


class StrategyPolicyValidationError(ValueError):
    """Raised when a selection.v2 policy or carrier is inconsistent."""


def _invalid(path: str, message: str) -> StrategyPolicyValidationError:
    return StrategyPolicyValidationError(f"{path} {message}")


def _require_fields(section: Mapping[str, Any], fields: set[str], *, path: str) -> None:
    missing = sorted(fields - section.keys())
    if missing:
        raise _invalid(path, f"is missing required fields: {missing}")


def _mapping(value: object, *, path: str, nonempty: bool = True) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(path, "must be a mapping")
    if nonempty and not value:
        raise _invalid(path, "must not be empty")
    return cast(dict[str, Any], value)


def _list(value: object, *, path: str, nonempty: bool = True) -> list[Any]:
    if not isinstance(value, list):
        raise _invalid(path, "must be a list")
    if nonempty and not value:
        raise _invalid(path, "must not be empty")
    return value


def _string(
    value: object,
    *,
    path: str,
    allowed: frozenset[str] | set[str] | None = None,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(path, "must be a non-empty string")
    if value != value.strip():
        raise _invalid(path, "must not contain surrounding whitespace")
    if allowed is not None and value not in allowed:
        raise _invalid(path, f"must be one of {sorted(allowed)}")
    return value


def _boolean(value: object, *, path: str) -> bool:
    if type(value) is not bool:
        raise _invalid(path, "must be a boolean")
    return value


def _integer(
    value: object,
    *,
    path: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise _invalid(path, "must be an integer (booleans are not integers)")
    number = value
    if minimum is not None and number < minimum:
        raise _invalid(path, f"must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise _invalid(path, f"must be <= {maximum}")
    return number


def _number(
    value: object,
    *,
    path: str,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_exclusive: bool = False,
    maximum_exclusive: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _invalid(path, "must be a number (booleans are not numbers)")
    number = float(value)
    if not math.isfinite(number):
        raise _invalid(path, "must be finite")
    if minimum is not None and (number <= minimum if minimum_exclusive else number < minimum):
        operator = ">" if minimum_exclusive else ">="
        raise _invalid(path, f"must be {operator} {minimum}")
    if maximum is not None and (number >= maximum if maximum_exclusive else number > maximum):
        operator = "<" if maximum_exclusive else "<="
        raise _invalid(path, f"must be {operator} {maximum}")
    return number


def _string_list(value: object, *, path: str) -> list[str]:
    values = _list(value, path=path)
    normalized = [_string(item, path=f"{path}[{index}]") for index, item in enumerate(values)]
    if len(set(normalized)) != len(normalized):
        raise _invalid(path, "must contain unique values")
    return normalized


def _validate_model_params(params: dict[str, Any], *, path: str) -> None:
    params_path = f"{path}.params"
    _require_fields(
        params,
        {
            "n_estimators",
            "learning_rate",
            "max_depth",
            "subsample",
            "colsample_bytree",
            "reg_alpha",
            "reg_lambda",
            "objective",
            "tree_method",
            "random_state",
        },
        path=params_path,
    )
    _integer(params["n_estimators"], path=f"{params_path}.n_estimators", minimum=1)
    _number(
        params["learning_rate"],
        path=f"{params_path}.learning_rate",
        minimum=0.0,
        minimum_exclusive=True,
    )
    _integer(params["max_depth"], path=f"{params_path}.max_depth", minimum=0)
    for field in ("subsample", "colsample_bytree"):
        _number(
            params[field],
            path=f"{params_path}.{field}",
            minimum=0.0,
            maximum=1.0,
            minimum_exclusive=True,
        )
    for field in ("reg_alpha", "reg_lambda"):
        _number(params[field], path=f"{params_path}.{field}", minimum=0.0)
    _string(params["objective"], path=f"{params_path}.objective", allowed={"rank:pairwise"})
    _string(params["tree_method"], path=f"{params_path}.tree_method", allowed={"hist"})
    _integer(params["random_state"], path=f"{params_path}.random_state")


def _validate_training_policy(model: dict[str, Any], *, path: str) -> None:
    policy_id = _string(model["training_policy_id"], path=f"{path}.training_policy_id")
    if len(policy_id) != 16 or any(character not in "0123456789abcdef" for character in policy_id):
        raise _invalid(f"{path}.training_policy_id", "must be a 16-character lowercase hex id")
    training = _mapping(model["training_policy"], path=f"{path}.training_policy")
    _require_fields(
        training,
        {"train_window_dates", "sample_weight_mode", "sample_weight_params", "min_query_size"},
        path=f"{path}.training_policy",
    )
    _integer(
        training["train_window_dates"],
        path=f"{path}.training_policy.train_window_dates",
        minimum=1,
    )
    _string(
        training["sample_weight_mode"],
        path=f"{path}.training_policy.sample_weight_mode",
        allowed={"exp_decay"},
    )
    weight_params = _mapping(
        training["sample_weight_params"],
        path=f"{path}.training_policy.sample_weight_params",
    )
    _require_fields(
        weight_params,
        {"halflife", "min_weight"},
        path=f"{path}.training_policy.sample_weight_params",
    )
    _number(
        weight_params["halflife"],
        path=f"{path}.training_policy.sample_weight_params.halflife",
        minimum=0.0,
        minimum_exclusive=True,
    )
    _number(
        weight_params["min_weight"],
        path=f"{path}.training_policy.sample_weight_params.min_weight",
        minimum=0.0,
        maximum=1.0,
    )
    _integer(
        training["min_query_size"],
        path=f"{path}.training_policy.min_query_size",
        minimum=2,
    )
    encoded = json.dumps(training, sort_keys=True, default=str).encode("utf-8")
    expected = hashlib.sha256(encoded).hexdigest()[:16]
    if policy_id != expected:
        raise _invalid(f"{path}.training_policy_id", "does not match training_policy")


def _validate_model(model: dict[str, Any]) -> None:
    path = "strategy_policy.model"
    _require_fields(
        model,
        {
            "name",
            "type",
            "params",
            "training_policy_id",
            "training_policy",
            "history_calendar_days",
            "retrain_weekdays",
            "max_model_age_trade_days",
        },
        path=path,
    )
    if _string(model["name"], path=f"{path}.name") != _MODEL_NAME:
        raise _invalid(f"{path}.name", f"must be {_MODEL_NAME}")
    _string(model["type"], path=f"{path}.type", allowed=_MODEL_TYPES)
    _validate_model_params(_mapping(model["params"], path=f"{path}.params"), path=path)
    _validate_training_policy(model, path=path)
    _integer(model["history_calendar_days"], path=f"{path}.history_calendar_days", minimum=1)
    weekdays = _list(model["retrain_weekdays"], path=f"{path}.retrain_weekdays")
    normalized_weekdays = [
        _integer(day, path=f"{path}.retrain_weekdays[{index}]", minimum=0, maximum=6)
        for index, day in enumerate(weekdays)
    ]
    if normalized_weekdays != sorted(set(normalized_weekdays)):
        raise _invalid(f"{path}.retrain_weekdays", "must be sorted and unique")
    _integer(
        model["max_model_age_trade_days"],
        path=f"{path}.max_model_age_trade_days",
        minimum=0,
    )


def _validate_features(features: dict[str, Any]) -> None:
    path = "strategy_policy.features"
    _require_fields(
        features,
        {
            "feature_timing_schema",
            "feature_policy_id",
            "feature_set_id",
            "ordered_model_features",
            "available_features",
            "minute_feature_schema",
            "minute_source_contract",
            "minute_transform_contract",
            "forward_days",
            "minute_lag_trade_days",
            "min_listed_days",
            "liquidity_floor_quantile",
            "date_col",
            "symbol_col",
            "price_col",
        },
        path=path,
    )
    if (
        _string(features["feature_timing_schema"], path=f"{path}.feature_timing_schema")
        != _FEATURE_TIMING_SCHEMA
    ):
        raise _invalid(f"{path}.feature_timing_schema", f"must be {_FEATURE_TIMING_SCHEMA}")
    policy_id = _string(features["feature_policy_id"], path=f"{path}.feature_policy_id")
    feature_set_id = _string(features["feature_set_id"], path=f"{path}.feature_set_id")
    if len(feature_set_id) != 16 or any(
        character not in "0123456789abcdef" for character in feature_set_id
    ):
        raise _invalid(f"{path}.feature_set_id", "must be a 16-character lowercase hex id")
    ordered = _string_list(
        features["ordered_model_features"], path=f"{path}.ordered_model_features"
    )
    available = _string_list(features["available_features"], path=f"{path}.available_features")
    if not set(ordered).issubset(available):
        raise _invalid(f"{path}.ordered_model_features", "must be a subset of available_features")
    expected_literals = {
        "minute_feature_schema": _MINUTE_FEATURE_SCHEMA,
        "minute_source_contract": _MINUTE_SOURCE_CONTRACT,
        "minute_transform_contract": _MINUTE_TRANSFORM_CONTRACT,
    }
    for field, expected in expected_literals.items():
        if _string(features[field], path=f"{path}.{field}") != expected:
            raise _invalid(f"{path}.{field}", f"must be {expected}")
    _integer(features["forward_days"], path=f"{path}.forward_days", minimum=1)
    minute_lag = _integer(
        features["minute_lag_trade_days"],
        path=f"{path}.minute_lag_trade_days",
        minimum=0,
    )
    _integer(features["min_listed_days"], path=f"{path}.min_listed_days", minimum=0)
    _number(
        features["liquidity_floor_quantile"],
        path=f"{path}.liquidity_floor_quantile",
        minimum=0.0,
        maximum=1.0,
        maximum_exclusive=True,
    )
    for field in ("date_col", "symbol_col", "price_col"):
        _string(features[field], path=f"{path}.{field}")
    expected_policy_id = (
        f"{_FEATURE_TIMING_SCHEMA}:minute_transform={_MINUTE_TRANSFORM_CONTRACT}:"
        f"minute_lag_trade_days={minute_lag}"
    )
    if features.get("data_regime") == "tushare_native_v1":
        expected_policy_id += ":data_regime=tushare_native_v1"
    if policy_id != expected_policy_id:
        raise _invalid(f"{path}.feature_policy_id", "does not match the feature timing contract")


def _validate_label(label: dict[str, Any], features: dict[str, Any]) -> None:
    path = "strategy_policy.label"
    _require_fields(
        label,
        {
            "policy_id",
            "forward_days",
            "horizon_weights",
            "label_col",
            "forward_return_col",
            "label_end_col",
            "feature_time",
            "entry_time",
            "entry_tradability",
            "exit_tradability",
        },
        path=path,
    )
    _string(label["policy_id"], path=f"{path}.policy_id")
    forward_days = _integer(label["forward_days"], path=f"{path}.forward_days", minimum=1)
    if forward_days != features["forward_days"]:
        raise _invalid(f"{path}.forward_days", "must match features.forward_days")
    raw_weights = _list(label["horizon_weights"], path=f"{path}.horizon_weights")
    horizons: list[int] = []
    weights: list[float] = []
    for index, raw_item in enumerate(raw_weights):
        item_path = f"{path}.horizon_weights[{index}]"
        item = _mapping(raw_item, path=item_path)
        _require_fields(item, {"trade_days", "weight"}, path=item_path)
        horizons.append(_integer(item["trade_days"], path=f"{item_path}.trade_days", minimum=1))
        weights.append(
            _number(
                item["weight"],
                path=f"{item_path}.weight",
                minimum=0.0,
                maximum=1.0,
                minimum_exclusive=True,
            )
        )
    if horizons != sorted(set(horizons)):
        raise _invalid(f"{path}.horizon_weights", "trade_days must be sorted and unique")
    if max(horizons) != forward_days:
        raise _invalid(f"{path}.forward_days", "must equal the longest label horizon")
    if not math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise _invalid(f"{path}.horizon_weights", "weights must sum to 1")
    for field in ("label_col", "forward_return_col", "label_end_col"):
        _string(label[field], path=f"{path}.{field}")
    expected_literals = {
        "feature_time": "source close",
        "entry_time": "next trade day open",
        "entry_tradability": "not suspended and not limit-up",
        "exit_tradability": "not suspended and not limit-down",
    }
    for field, expected in expected_literals.items():
        if _string(label[field], path=f"{path}.{field}") != expected:
            raise _invalid(f"{path}.{field}", f"must be {expected}")
    expected_label_col = (
        f"forward_rank_{horizons[0]}d" if len(horizons) == 1 else "forward_rank_blended"
    )
    expected_return_col = (
        f"forward_return_{horizons[0]}d" if len(horizons) == 1 else "forward_return_blended"
    )
    if (
        label["label_col"] != expected_label_col
        or label["forward_return_col"] != expected_return_col
    ):
        raise _invalid(path, "label columns do not match horizon_weights")
    feature_set_payload = {
        "features": features["ordered_model_features"],
        "feature_policy_id": features["feature_policy_id"],
        "label": label["label_col"],
        "forward_days": forward_days,
        "label_horizon_weights": [list(item) for item in zip(horizons, weights, strict=True)],
        "label_policy_id": label["policy_id"],
    }
    encoded = json.dumps(feature_set_payload, sort_keys=True, default=str).encode("utf-8")
    expected_feature_set_id = hashlib.sha256(encoded).hexdigest()[:16]
    if features["feature_set_id"] != expected_feature_set_id:
        raise _invalid(
            "strategy_policy.features.feature_set_id",
            "does not match the model feature and label contract",
        )


def _expected_candidate_policy_id(mode: str, minimum: int, snapshot_minimum: int) -> str:
    if mode == "all_market":
        return _ALL_MARKET_POLICY_ID
    suffix = (
        f"{_THS_HOT_POLICY_SCHEMAS[mode]}:min_symbols={minimum}:"
        f"snapshot_min_symbols={snapshot_minimum}:close_cutoff_minute=900:"
        "max_snapshot_fallback_minutes=60"
    )
    if mode in {"ths_hot_strict_v2", "ths_hot_strict_v3"}:
        required_top_ranks = 20 if mode == "ths_hot_strict_v2" else 1
        suffix += (
            ":batch_gap_seconds=15:max_component_span_seconds=180:"
            f"max_missing_ranks={_THS_HOT_V2_MAX_MISSING_RANKS}:"
            f"max_snapshot_symbols={_THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS}:"
            f"require_rank_one=true:required_top_ranks={required_top_ranks}"
        )
    return suffix


def _validate_candidate_pool(candidate: dict[str, Any]) -> None:
    path = "strategy_policy.candidate_pool"
    _require_fields(
        candidate,
        {
            "mode",
            "policy_id",
            "restricted",
            "fail_closed",
            "positive_change_only",
            "min_symbols",
            "snapshot_min_symbols",
        },
        path=path,
    )
    mode = _string(candidate["mode"], path=f"{path}.mode", allowed=_CANDIDATE_MODES)
    if mode in {"ths_hot_strict_v2", "ths_hot_strict_v3"}:
        if "max_missing_ranks" not in candidate:
            raise _invalid(path, "is missing required fields: ['max_missing_ranks']")
        if (
            _integer(
                candidate["max_missing_ranks"],
                path=f"{path}.max_missing_ranks",
                minimum=0,
            )
            != _THS_HOT_V2_MAX_MISSING_RANKS
        ):
            raise _invalid(
                f"{path}.max_missing_ranks",
                f"must be {_THS_HOT_V2_MAX_MISSING_RANKS}",
            )
    elif "max_missing_ranks" in candidate:
        raise _invalid(
            f"{path}.max_missing_ranks",
            "is only valid in sparse strict candidate-pool modes",
        )
    policy_id = _string(candidate["policy_id"], path=f"{path}.policy_id")
    restricted = _boolean(candidate["restricted"], path=f"{path}.restricted")
    fail_closed = _boolean(candidate["fail_closed"], path=f"{path}.fail_closed")
    positive = _boolean(candidate["positive_change_only"], path=f"{path}.positive_change_only")
    expected_restricted = mode != "all_market"
    if restricted is not expected_restricted or fail_closed is not expected_restricted:
        raise _invalid(path, "restricted and fail_closed must match candidate-pool mode")
    if positive is not expected_restricted:
        raise _invalid(f"{path}.positive_change_only", "must match candidate-pool mode")
    if expected_restricted:
        minimum = _integer(candidate["min_symbols"], path=f"{path}.min_symbols", minimum=20)
        snapshot_minimum = _integer(
            candidate["snapshot_min_symbols"],
            path=f"{path}.snapshot_min_symbols",
            minimum=minimum,
        )
        if (
            mode in {"ths_hot_strict_v2", "ths_hot_strict_v3"}
            and snapshot_minimum > _THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS
        ):
            raise _invalid(
                f"{path}.snapshot_min_symbols",
                f"must be <= {_THS_HOT_V2_MAX_SNAPSHOT_SYMBOLS} in sparse strict modes",
            )
    else:
        if candidate["min_symbols"] is not None or candidate["snapshot_min_symbols"] is not None:
            raise _invalid(path, "all_market symbol thresholds must be null")
        minimum = 0
        snapshot_minimum = 0
    expected_id = _expected_candidate_policy_id(mode, minimum, snapshot_minimum)
    if policy_id != expected_id:
        raise _invalid(f"{path}.policy_id", "does not match candidate-pool settings")


def _validate_news_heat(news: dict[str, Any]) -> None:
    path = "strategy_policy.news_heat"
    _require_fields(
        news,
        {
            "schema_version",
            "configured_enabled",
            "effective_enabled",
            "minimum_rows",
            "coverage_mode",
            "missing_symbol_semantics",
        },
        path=path,
    )
    if _string(news["schema_version"], path=f"{path}.schema_version") != _NEWS_HEAT_SCHEMA:
        raise _invalid(f"{path}.schema_version", f"must be {_NEWS_HEAT_SCHEMA}")
    configured = _boolean(news["configured_enabled"], path=f"{path}.configured_enabled")
    effective = _boolean(news["effective_enabled"], path=f"{path}.effective_enabled")
    if effective and not configured:
        raise _invalid(f"{path}.effective_enabled", "cannot be true when configured_enabled=false")
    _integer(news["minimum_rows"], path=f"{path}.minimum_rows", minimum=1)
    expected_literals = {
        "coverage_mode": "sparse_positive_only",
        "missing_symbol_semantics": "neutral_unknown",
    }
    for field, expected in expected_literals.items():
        if _string(news[field], path=f"{path}.{field}") != expected:
            raise _invalid(f"{path}.{field}", f"must be {expected}")


def _validate_guard_factors(
    construction: dict[str, Any], news: dict[str, Any], *, path: str
) -> None:
    raw_factors = _list(construction["guard_factors"], path=f"{path}.guard_factors")
    columns: list[str] = []
    factor_weights: list[float] = []
    for index, raw_factor in enumerate(raw_factors):
        factor_path = f"{path}.guard_factors[{index}]"
        factor = _mapping(raw_factor, path=factor_path)
        _require_fields(factor, {"column", "weight", "higher_is_better"}, path=factor_path)
        columns.append(_string(factor["column"], path=f"{factor_path}.column"))
        factor_weights.append(
            _number(
                factor["weight"],
                path=f"{factor_path}.weight",
                minimum=0.0,
                maximum=1.0,
                minimum_exclusive=True,
            )
        )
        _boolean(factor["higher_is_better"], path=f"{factor_path}.higher_is_better")
    if len(set(columns)) != len(columns):
        raise _invalid(f"{path}.guard_factors", "columns must be unique")
    if not math.isclose(sum(factor_weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise _invalid(f"{path}.guard_factors", "weights must sum to 1")
    if ("news_heat_guard" in columns) is not news["effective_enabled"]:
        raise _invalid(
            f"{path}.guard_factors",
            "news_heat_guard presence must match news_heat.effective_enabled",
        )


def _validate_construction_weights(construction: dict[str, Any], *, path: str) -> None:
    ml_weight = _number(
        construction["ml_weight"], path=f"{path}.ml_weight", minimum=0.0, maximum=1.0
    )
    guard_weight = _number(
        construction["guard_weight"], path=f"{path}.guard_weight", minimum=0.0, maximum=1.0
    )
    if not math.isclose(ml_weight + guard_weight, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise _invalid(path, "ml_weight and guard_weight must sum to 1")
    _integer(construction["industry_cap"], path=f"{path}.industry_cap", minimum=1)
    _integer(construction["b_retention_buffer"], path=f"{path}.b_retention_buffer", minimum=0)
    max_replacements = _integer(
        construction["b_max_replacements"], path=f"{path}.b_max_replacements", minimum=0
    )
    a_weight = _number(
        construction["a_tracking_weight"],
        path=f"{path}.a_tracking_weight",
        minimum=0.0,
        maximum=1.0,
    )
    _string(construction["fallback_mode"], path=f"{path}.fallback_mode", allowed={"none"})
    sleeves = _mapping(construction["sleeves"], path=f"{path}.sleeves")
    _require_fields(sleeves, {"A", "B"}, path=f"{path}.sleeves")
    sleeve_a = _integer(sleeves["A"], path=f"{path}.sleeves.A", minimum=1)
    sleeve_b = _integer(sleeves["B"], path=f"{path}.sleeves.B", minimum=1)
    if (sleeve_a, sleeve_b) != (4, 16):
        raise _invalid(f"{path}.sleeves", "must be the DailyWatch20 4+16 construction")
    if max_replacements > sleeve_b:
        raise _invalid(f"{path}.b_max_replacements", "must not exceed sleeve B size")
    if not math.isclose(a_weight, sleeve_a / (sleeve_a + sleeve_b), abs_tol=1e-12):
        raise _invalid(f"{path}.a_tracking_weight", "must match sleeve A's equal-weight share")


def _validate_construction(construction: dict[str, Any], news: dict[str, Any]) -> None:
    path = "strategy_policy.construction"
    _require_fields(
        construction,
        {
            "schema_version",
            "date_col",
            "symbol_col",
            "industry_col",
            "ml_score_col",
            "hard_eligibility_col",
            "guard_factors",
            "ml_weight",
            "guard_weight",
            "industry_cap",
            "b_retention_buffer",
            "b_max_replacements",
            "a_tracking_weight",
            "fallback_mode",
            "sleeves",
        },
        path=path,
    )
    if (
        _string(construction["schema_version"], path=f"{path}.schema_version")
        != _CONSTRUCTION_SCHEMA
    ):
        raise _invalid(f"{path}.schema_version", f"must be {_CONSTRUCTION_SCHEMA}")
    for field in ("date_col", "symbol_col", "industry_col", "ml_score_col", "hard_eligibility_col"):
        _string(construction[field], path=f"{path}.{field}")
    _validate_guard_factors(construction, news, path=path)
    _validate_construction_weights(construction, path=path)


def _validate_policy_safety(safety: dict[str, Any]) -> None:
    path = "strategy_policy.safety"
    _require_fields(
        safety,
        {
            "market_scope",
            "eligible_for_backtest",
            "eligible_for_live",
            "publication_tier",
            "publication_timezone",
            "publication_window_start",
            "publication_window_end_exclusive",
        },
        path=path,
    )
    if _string(safety["market_scope"], path=f"{path}.market_scope") != "sh-sz":
        raise _invalid(f"{path}.market_scope", "must be sh-sz")
    _boolean(safety["eligible_for_backtest"], path=f"{path}.eligible_for_backtest")
    if _boolean(safety["eligible_for_live"], path=f"{path}.eligible_for_live") is not False:
        raise _invalid(f"{path}.eligible_for_live", "must be false")
    _string(
        safety["publication_tier"],
        path=f"{path}.publication_tier",
        allowed={"production", "research"},
    )
    expected_literals = {
        "publication_timezone": _PUBLICATION_TIMEZONE,
        "publication_window_start": _PUBLICATION_WINDOW_START,
        "publication_window_end_exclusive": _PUBLICATION_WINDOW_END,
    }
    for field, expected in expected_literals.items():
        if _string(safety[field], path=f"{path}.{field}") != expected:
            raise _invalid(f"{path}.{field}", f"must be {expected}")


def validate_strategy_policy(policy: dict[str, Any]) -> None:
    model = _mapping(policy["model"], path="strategy_policy.model")
    features = _mapping(policy["features"], path="strategy_policy.features")
    label = _mapping(policy["label"], path="strategy_policy.label")
    candidate = _mapping(policy["candidate_pool"], path="strategy_policy.candidate_pool")
    news = _mapping(policy["news_heat"], path="strategy_policy.news_heat")
    construction = _mapping(policy["construction"], path="strategy_policy.construction")
    safety = _mapping(policy["safety"], path="strategy_policy.safety")
    _validate_model(model)
    _validate_features(features)
    _validate_label(label, features)
    _validate_candidate_pool(candidate)
    _validate_news_heat(news)
    _validate_construction(construction, news)
    _validate_policy_safety(safety)
    for field in ("date_col", "symbol_col"):
        if construction[field] != features[field]:
            raise _invalid(
                f"strategy_policy.construction.{field}",
                f"must match features.{field}",
            )
    allowed_guard_columns = set(features["available_features"])
    if news["effective_enabled"]:
        allowed_guard_columns.add("news_heat_guard")
    guard_columns = {factor["column"] for factor in construction["guard_factors"]}
    if not guard_columns.issubset(allowed_guard_columns):
        raise _invalid(
            "strategy_policy.construction.guard_factors",
            "columns must be available features or the effective news-heat guard",
        )
    if safety["publication_tier"] == "production":
        if candidate["mode"] not in {"all_market", "ths_hot_strict_v2", "ths_hot_strict_v3"}:
            raise _invalid(
                "strategy_policy.candidate_pool.mode",
                "must use all_market or an approved sparse strict mode for production publication",
            )
        if "hermite_stability" in features["ordered_model_features"]:
            raise _invalid(
                "strategy_policy.features.ordered_model_features",
                "must exclude hermite_stability for production publication",
            )


__all__ = ["StrategyPolicyValidationError", "validate_strategy_policy"]
