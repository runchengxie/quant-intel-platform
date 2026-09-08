"""Candidate-pool validation contracts for DailyWatch20.

Pure physical split of ``a_share_daily.daily_watch20``; see ``_common`` for the
shared base helpers and constants.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

import pandas as pd

from ..daily_watch20_candidate_pool import (
    THS_HOT_STRICT_V2,
    THS_HOT_STRICT_V3,
    THSHotV2ValidationError,
    validate_ths_hot_strict_v2,
    validate_ths_hot_strict_v3,
)
from ._common import (
    EXPECTED_TOTAL,
    THS_HOT_CLOSE_CUTOFF_MINUTE,
    THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES,
    THS_HOT_POLICY_SCHEMA,
    DailyWatch20ValidationError,
)


def _strict_candidate_pool_counts(candidate_pool: Mapping[str, Any]) -> dict[str, int]:
    numeric_fields = (
        "min_symbols",
        "snapshot_min_symbols",
        "close_cutoff_minute",
        "max_snapshot_fallback_minutes",
        "snapshot_unique_symbols",
        "pool_symbols",
        "eligible_intersection_symbols",
    )
    counts: dict[str, int] = {}
    for field in numeric_fields:
        try:
            counts[field] = int(str(candidate_pool.get(field)))
        except (TypeError, ValueError) as exc:
            raise DailyWatch20ValidationError(f"receipt.candidate_pool.{field} is invalid") from exc
    if counts["min_symbols"] < EXPECTED_TOTAL:
        raise DailyWatch20ValidationError(
            f"receipt.candidate_pool.min_symbols must be at least {EXPECTED_TOTAL}"
        )
    if counts["snapshot_min_symbols"] < counts["min_symbols"]:
        raise DailyWatch20ValidationError(
            "receipt.candidate_pool.snapshot_min_symbols must be at least min_symbols"
        )
    if counts["close_cutoff_minute"] != THS_HOT_CLOSE_CUTOFF_MINUTE:
        raise DailyWatch20ValidationError("receipt.candidate_pool.close_cutoff_minute is invalid")
    if counts["max_snapshot_fallback_minutes"] != THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES:
        raise DailyWatch20ValidationError(
            "receipt.candidate_pool.max_snapshot_fallback_minutes is invalid"
        )
    if counts["snapshot_unique_symbols"] < counts["snapshot_min_symbols"]:
        raise DailyWatch20ValidationError(
            "receipt.candidate_pool.snapshot_unique_symbols is too small"
        )
    if counts["pool_symbols"] < counts["min_symbols"]:
        raise DailyWatch20ValidationError("receipt.candidate_pool.pool_symbols is too small")
    if counts["eligible_intersection_symbols"] < EXPECTED_TOTAL:
        raise DailyWatch20ValidationError(
            "receipt.candidate_pool.eligible_intersection_symbols "
            f"must be at least {EXPECTED_TOTAL}"
        )
    return counts


def _validate_strict_candidate_pool_metadata(
    candidate_pool: Mapping[str, Any], *, source_date: str
) -> None:
    if candidate_pool.get("source") != "tushare.ths_hot":
        raise DailyWatch20ValidationError("receipt.candidate_pool.source is invalid")
    if candidate_pool.get("restricted") is not True:
        raise DailyWatch20ValidationError("receipt.candidate_pool must be restricted")
    if not str(candidate_pool.get("root") or "").strip():
        raise DailyWatch20ValidationError("receipt.candidate_pool.root is required")
    if str(candidate_pool.get("source_date") or "").replace("-", "") != source_date:
        raise DailyWatch20ValidationError("receipt.candidate_pool.source_date mismatch")
    if candidate_pool.get("fail_closed") is not True:
        raise DailyWatch20ValidationError("receipt.candidate_pool must be fail-closed")
    if candidate_pool.get("positive_change_only") is not True:
        raise DailyWatch20ValidationError("receipt.candidate_pool must require positive change")
    counts = _strict_candidate_pool_counts(candidate_pool)
    expected_policy_id = (
        f"{THS_HOT_POLICY_SCHEMA}:"
        f"min_symbols={counts['min_symbols']}:"
        f"snapshot_min_symbols={counts['snapshot_min_symbols']}:"
        f"close_cutoff_minute={THS_HOT_CLOSE_CUTOFF_MINUTE}:"
        "max_snapshot_fallback_minutes="
        f"{THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES}"
    )
    if candidate_pool.get("policy_id") != expected_policy_id:
        raise DailyWatch20ValidationError("receipt.candidate_pool.policy_id is invalid")


def _validate_strict_candidate_pool_selection(receipt: Mapping[str, Any]) -> None:
    construction = receipt.get("construction")
    if (
        not isinstance(construction, Mapping)
        or "selected_outside_candidate_pool" not in construction
    ):
        raise DailyWatch20ValidationError(
            "receipt.construction.selected_outside_candidate_pool is required"
        )
    try:
        selected_outside = int(str(construction["selected_outside_candidate_pool"]))
    except (TypeError, ValueError) as exc:
        raise DailyWatch20ValidationError(
            "receipt.construction.selected_outside_candidate_pool is invalid"
        ) from exc
    if selected_outside != 0:
        raise DailyWatch20ValidationError("watchlist contains symbols outside candidate_pool")


def _normalize_strict_candidate_pool_rows(frame: pd.DataFrame, *, source_date: str) -> None:
    required_columns = {"ths_hot_rank", "ths_hot_pct_change", "ths_hot_rank_time"}
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise DailyWatch20ValidationError(
            f"strict THS-hot watchlist missing columns: {', '.join(missing)}"
        )
    ranks = cast(pd.Series, pd.to_numeric(frame["ths_hot_rank"], errors="coerce"))
    changes = cast(pd.Series, pd.to_numeric(frame["ths_hot_pct_change"], errors="coerce"))
    if (
        bool(ranks.isna().any())
        or not bool(ranks.map(math.isfinite).all())
        or bool(ranks.le(0).any())
        or bool(ranks.mod(1).ne(0).any())
    ):
        raise DailyWatch20ValidationError("ths_hot_rank must contain positive integers")
    if (
        bool(changes.isna().any())
        or not bool(changes.map(math.isfinite).all())
        or not bool(changes.gt(0).all())
    ):
        raise DailyWatch20ValidationError("ths_hot_pct_change must be positive")
    rank_times = cast(pd.Series, pd.to_datetime(frame["ths_hot_rank_time"], errors="coerce"))
    if bool(rank_times.isna().any()) or set(rank_times.dt.strftime("%Y%m%d")) != {source_date}:
        raise DailyWatch20ValidationError("ths_hot_rank_time must match source_date")
    frame["ths_hot_rank"] = ranks.astype(int)
    frame["ths_hot_pct_change"] = changes.astype(float)
    frame["ths_hot_rank_time"] = rank_times


def _validate_candidate_pool_contract(
    receipt: Mapping[str, Any],
    frame: pd.DataFrame,
    *,
    source_date: str,
    expected_mode: str | None,
) -> None:
    candidate_pool = receipt.get("candidate_pool")
    if expected_mode is None:
        if not isinstance(candidate_pool, Mapping) or candidate_pool.get("mode") not in {
            THS_HOT_STRICT_V2,
            THS_HOT_STRICT_V3,
        }:
            return
        expected_mode = str(candidate_pool.get("mode"))
    if not isinstance(candidate_pool, Mapping):
        raise DailyWatch20ValidationError("receipt.candidate_pool is required")
    if candidate_pool.get("mode") != expected_mode:
        raise DailyWatch20ValidationError(f"receipt.candidate_pool.mode must be {expected_mode}")
    if expected_mode == "all_market":
        if len(frame) != 20 or frame["symbol"].nunique() != 20:
            raise DailyWatch20ValidationError(
                "all-market DailyWatch20 watchlist must contain 20 unique stocks"
            )
        return
    if expected_mode not in {"ths_hot_strict", THS_HOT_STRICT_V2, THS_HOT_STRICT_V3}:
        raise DailyWatch20ValidationError(
            f"unsupported expected candidate-pool mode: {expected_mode}"
        )
    _validate_strict_candidate_pool_selection(receipt)
    _normalize_strict_candidate_pool_rows(frame, source_date=source_date)
    if expected_mode == "ths_hot_strict":
        _validate_strict_candidate_pool_metadata(candidate_pool, source_date=source_date)
        return
    try:
        validator = (
            validate_ths_hot_strict_v3
            if expected_mode == THS_HOT_STRICT_V3
            else validate_ths_hot_strict_v2
        )
        validator(receipt, frame, source_date=source_date)
    except THSHotV2ValidationError as exc:
        raise DailyWatch20ValidationError(str(exc)) from exc


__all__ = [
    "_strict_candidate_pool_counts",
    "_validate_strict_candidate_pool_metadata",
    "_validate_strict_candidate_pool_selection",
    "_normalize_strict_candidate_pool_rows",
    "_validate_candidate_pool_contract",
]
