"""Frame, artifact, companion, and minute validation contracts for DailyWatch20.

Pure physical split of ``a_share_daily.daily_watch20``; see ``_common`` for the
shared base helpers and constants.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from ._common import (
    EXPECTED_SLEEVE_COUNTS,
    EXPECTED_TOTAL,
    WATCHLIST_SCHEMA_V2,
    WEIGHT_TOLERANCE,
    DailyWatch20ValidationError,
    _core_rows,
    _date_key,
    _normalize_watchlist_frame,
    _parse_bool,
    _read_watchlist_frame,
    _sha256,
)
from .receipt_contract import _required_minute_date


def _validate_minute_receipt(
    receipt: Mapping[str, Any],
    *,
    source_date: str,
    trade_calendar_path: Path,
    expected_lag_trade_days: int,
) -> None:
    minute = receipt.get("minute_features")
    if not isinstance(minute, Mapping):
        raise DailyWatch20ValidationError("receipt.minute_features is required")
    missing = [
        key for key in ("enabled", "as_of", "required_date", "lag_trade_days") if key not in minute
    ]
    if missing:
        raise DailyWatch20ValidationError(
            "receipt.minute_features missing fields: " + ", ".join(missing)
        )
    enabled = _parse_bool(minute.get("enabled"))
    if not enabled:
        raise DailyWatch20ValidationError("receipt.minute_features must be enabled")
    as_of_raw = minute.get("as_of")
    if enabled and not as_of_raw:
        raise DailyWatch20ValidationError("receipt.minute_features.as_of is required when enabled")
    if as_of_raw:
        as_of = _date_key(as_of_raw, field="receipt.minute_features.as_of")
        if as_of > source_date:
            raise DailyWatch20ValidationError("minute feature as_of cannot be after source_date")
        required = _date_key(
            minute.get("required_date"), field="receipt.minute_features.required_date"
        )
        if required > source_date:
            raise DailyWatch20ValidationError(
                "minute feature required_date cannot exceed source_date"
            )
        if as_of < required:
            raise DailyWatch20ValidationError("minute feature cache is stale for required_date")
    try:
        lag = int(str(minute.get("lag_trade_days")))
    except (TypeError, ValueError) as exc:
        raise DailyWatch20ValidationError("minute_features.lag_trade_days is invalid") from exc
    if lag < 0:
        raise DailyWatch20ValidationError("minute_features.lag_trade_days must be >= 0")
    if lag != expected_lag_trade_days:
        raise DailyWatch20ValidationError(
            f"minute_features.lag_trade_days must be {expected_lag_trade_days}, got {lag}"
        )
    expected_required = _required_minute_date(
        trade_calendar_path, source_date, expected_lag_trade_days
    )
    required = _date_key(minute.get("required_date"), field="receipt.minute_features.required_date")
    if required != expected_required:
        raise DailyWatch20ValidationError(
            f"minute feature required_date must be {expected_required}, got {required}"
        )


def _validate_artifact_inventory(root: Path, receipt: Mapping[str, Any]) -> None:
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise DailyWatch20ValidationError("receipt.artifacts is required")
    if "watchlist_20.csv" not in artifacts:
        raise DailyWatch20ValidationError("receipt.artifacts must protect watchlist_20.csv")
    for name, raw in artifacts.items():
        if not isinstance(raw, Mapping):
            raise DailyWatch20ValidationError(f"receipt artifact entry is invalid: {name}")
        relative = Path(str(raw.get("path") or name))
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            raise DailyWatch20ValidationError(f"receipt artifact escapes root: {name}")
        if not candidate.is_file():
            raise DailyWatch20ValidationError(f"receipt artifact is missing: {name}")
        expected = str(raw.get("sha256") or "")
        if not expected or _sha256(candidate) != expected:
            raise DailyWatch20ValidationError(f"receipt artifact hash mismatch: {name}")


def _check_frame_shape(frame: pd.DataFrame) -> None:
    if len(frame) != EXPECTED_TOTAL:
        raise DailyWatch20ValidationError(f"watchlist must contain 20 rows, got {len(frame)}")
    if frame["symbol"].nunique() != EXPECTED_TOTAL:
        raise DailyWatch20ValidationError("watchlist must contain 20 unique symbols")
    if not frame["symbol"].str.fullmatch(r"\d{6}\.(SH|SZ)").all():
        raise DailyWatch20ValidationError("watchlist symbols must be six-digit SH/SZ codes")
    counts = frame["sleeve"].value_counts().to_dict()
    if counts != EXPECTED_SLEEVE_COUNTS:
        raise DailyWatch20ValidationError(f"watchlist sleeve counts must be A4/B16, got {counts}")
    if frame.duplicated(subset=["sleeve", "rank"]).any():
        raise DailyWatch20ValidationError("rank must be unique within each sleeve")
    for sleeve, count in EXPECTED_SLEEVE_COUNTS.items():
        actual_ranks = set(frame.loc[frame["sleeve"] == sleeve, "rank"])
        expected_ranks = set(range(1, count + 1))
        if actual_ranks != expected_ranks:
            raise DailyWatch20ValidationError(f"{sleeve} ranks must be 1..{count}")


def _check_frame_dates(
    frame: pd.DataFrame,
    *,
    source_date: str,
    signal_date: str,
    schema_version: str,
) -> None:
    if set(frame["source_date"]) != {source_date}:
        raise DailyWatch20ValidationError("row source_date does not match receipt")
    if set(frame["signal_date"]) != {signal_date}:
        raise DailyWatch20ValidationError("row signal_date does not match receipt")
    if (frame["data_as_of"] > source_date).any():
        raise DailyWatch20ValidationError("row data_as_of cannot be after source_date")
    if schema_version == WATCHLIST_SCHEMA_V2 and set(frame["data_as_of"]) != {source_date}:
        raise DailyWatch20ValidationError("v2 row data_as_of must match receipt source_date")


def _check_frame_weights(frame: pd.DataFrame) -> None:
    weight_sum = float(frame["tracking_weight"].sum())
    if not math.isclose(weight_sum, 1.0, abs_tol=WEIGHT_TOLERANCE):
        raise DailyWatch20ValidationError(
            f"watchlist tracking_weight must sum to 1.0, got {weight_sum:.10g}"
        )


def _check_frame_receipt_fields(
    frame: pd.DataFrame, receipt: Mapping[str, Any], *, schema_version: str
) -> None:
    for field in ("model_version", "feature_set_id"):
        expected = str(receipt.get(field) or "").strip()
        if not expected:
            raise DailyWatch20ValidationError(f"receipt.{field} is required")
        if set(frame[field]) != {expected}:
            raise DailyWatch20ValidationError(f"row {field} does not match receipt")
    if schema_version == WATCHLIST_SCHEMA_V2:
        expected_policy_id = str(receipt.get("strategy_policy_id") or "").strip()
        if set(frame["strategy_policy_id"]) != {expected_policy_id}:
            raise DailyWatch20ValidationError("row strategy_policy_id does not match receipt")


def _validate_frame_contract(
    frame: pd.DataFrame,
    receipt: Mapping[str, Any],
    *,
    source_date: str,
    signal_date: str,
    schema_version: str,
) -> None:
    _check_frame_shape(frame)
    _check_frame_dates(
        frame, source_date=source_date, signal_date=signal_date, schema_version=schema_version
    )
    _check_frame_weights(frame)
    _check_frame_receipt_fields(frame, receipt, schema_version=schema_version)


def _validate_companion_json(
    csv_frame: pd.DataFrame, json_path: Path, *, schema_version: str
) -> None:
    json_frame = _normalize_watchlist_frame(
        _read_watchlist_frame(json_path), schema_version=schema_version
    )
    if _core_rows(csv_frame) != _core_rows(json_frame):
        raise DailyWatch20ValidationError("watchlist_20.csv and watchlist_20.json disagree")
    if schema_version == WATCHLIST_SCHEMA_V2 and set(json_frame["strategy_policy_id"]) != set(
        csv_frame["strategy_policy_id"]
    ):
        raise DailyWatch20ValidationError(
            "watchlist_20.json strategy_policy_id does not match receipt"
        )


__all__ = [
    "_validate_minute_receipt",
    "_validate_artifact_inventory",
    "_validate_frame_contract",
    "_validate_companion_json",
]
