"""Shared constants and base helpers for DailyWatch20 validation.

This subpackage is a pure physical split of ``a_share_daily.daily_watch20``.
Nothing here is part of the public API surface; the re-exports in
``daily_watch20`` preserve backward compatibility for any caller that imported
a ``_validate_*`` symbol directly.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from ops_common.env import resolve_data_platform_root

DEFAULT_WATCHLIST20_ROOT = Path(
    ".market-intel-external-data-not-configured/strategy_outputs/watchlist20/latest"
)
WATCHLIST_SCHEMA_V1 = "daily_watch20.selection.v1"
WATCHLIST_SCHEMA_V2 = "daily_watch20.selection.v2"
WATCHLIST_SCHEMAS = frozenset({WATCHLIST_SCHEMA_V1, WATCHLIST_SCHEMA_V2})
RECEIPT_FILENAMES = ("selection_receipt.json",)
DATA_FILENAMES = ("watchlist_20.csv",)
EXPECTED_TOTAL = 20
EXPECTED_SLEEVE_COUNTS = {"A": 4, "B": 16}
WEIGHT_TOLERANCE = 1e-6
THS_HOT_POLICY_SCHEMA = "daily_watch20.ths_hot_positive_close.v1"
THS_HOT_CLOSE_CUTOFF_MINUTE = 15 * 60
THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES = 60

_DATE_FIELDS = ("signal_date", "source_date", "data_as_of")
_REQUIRED_COLUMNS = (
    "signal_date",
    "source_date",
    "symbol",
    "name",
    "sleeve",
    "rank",
    "tracking_weight",
    "xgb_score",
    "xgb_percentile",
    "guard_score",
    "final_score",
    "industry",
    "theme",
    "dual_confirmed",
    "is_new",
    "top_drivers",
    "primary_risk",
    "model_version",
    "feature_set_id",
    "data_as_of",
)
_SCORE_COLUMNS = ("xgb_score", "xgb_percentile", "guard_score", "final_score")
_BOOL_COLUMNS = ("dual_confirmed", "is_new")


class DailyWatch20ValidationError(ValueError):
    """Raised when the artifact cannot be trusted for delivery."""


def resolve_watchlist20_root(explicit: str | Path | None = None) -> Path:
    raw = explicit or os.environ.get("WATCHLIST20_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return (
        resolve_data_platform_root(required=True) / "strategy_outputs" / "watchlist20" / "latest"
    ).resolve()


def _date_key(value: Any, *, field: str) -> str:
    text = str(value or "").strip().replace("-", "")
    if not re.fullmatch(r"\d{8}", text):
        raise DailyWatch20ValidationError(f"{field} must be YYYYMMDD, got {value!r}")
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise DailyWatch20ValidationError(f"{field} is not a valid date: {text}") from exc
    return text


def _date_dash(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _load_json_mapping(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyWatch20ValidationError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DailyWatch20ValidationError(f"{label} must be a JSON object: {path}")
    return payload


def _resolve_existing(root: Path, names: Sequence[str], *, label: str) -> Path:
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return candidate
    joined = ", ".join(names)
    raise DailyWatch20ValidationError(f"{label} missing under {root}; expected one of: {joined}")


def _rows_from_json_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("watchlist", "positions", "items", "rows", "data"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _read_watchlist_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False)
        except (OSError, pd.errors.ParserError) as exc:
            raise DailyWatch20ValidationError(f"cannot read watchlist CSV: {path}: {exc}") from exc
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyWatch20ValidationError(f"cannot read watchlist JSON: {path}: {exc}") from exc
    rows = _rows_from_json_payload(payload)
    if not rows:
        raise DailyWatch20ValidationError(f"watchlist JSON contains no rows: {path}")
    return pd.DataFrame(rows)


def _parse_weight(value: Any) -> float:
    text = str(value or "").strip()
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    try:
        number = float(text)
    except ValueError as exc:
        raise DailyWatch20ValidationError(f"invalid tracking_weight: {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise DailyWatch20ValidationError(
            f"tracking_weight must be finite and non-negative: {value!r}"
        )
    return number / 100.0 if percent else number


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"", "0", "false", "no", "n", "off", "none", "nan"}:
        return False
    raise DailyWatch20ValidationError(f"invalid boolean value: {value!r}")


def _normalize_sleeve(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("A"):
        return "A"
    if text.startswith("B"):
        return "B"
    raise DailyWatch20ValidationError(f"sleeve must be A or B, got {value!r}")


def _require_columns(frame: pd.DataFrame, *, schema_version: str) -> None:
    required = _REQUIRED_COLUMNS + (
        ("strategy_policy_id",) if schema_version == WATCHLIST_SCHEMA_V2 else ()
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DailyWatch20ValidationError(
            f"watchlist missing required columns: {', '.join(missing)}"
        )


def _normalize_watchlist_frame(frame: pd.DataFrame, *, schema_version: str) -> pd.DataFrame:
    _require_columns(frame, schema_version=schema_version)
    out = frame.copy()
    for column in _DATE_FIELDS:
        out[column] = out[column].map(lambda value, name=column: _date_key(value, field=name))
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()
    out["name"] = out["name"].astype(str).str.strip()
    if bool(out["name"].eq("").any()):
        raise DailyWatch20ValidationError("name must be non-empty")
    out["sleeve"] = out["sleeve"].map(_normalize_sleeve)
    out["tracking_weight"] = out["tracking_weight"].map(_parse_weight)
    ranks = cast(pd.Series, pd.to_numeric(out["rank"], errors="coerce"))
    out["rank"] = ranks
    if bool(ranks.isna().any()) or bool(ranks.le(0).any()):
        raise DailyWatch20ValidationError("rank must contain positive integers")
    if bool(ranks.mod(1).ne(0).any()):
        raise DailyWatch20ValidationError("rank must contain integers")
    out["rank"] = out["rank"].astype(int)
    for column in _SCORE_COLUMNS:
        scores = cast(pd.Series, pd.to_numeric(out[column], errors="coerce"))
        if bool(scores.isna().any()) or not bool(scores.map(math.isfinite).all()):
            raise DailyWatch20ValidationError(f"{column} must contain finite numbers")
        out[column] = scores
    for column in _BOOL_COLUMNS:
        out[column] = out[column].map(_parse_bool)
    for column in (
        "industry",
        "theme",
        "top_drivers",
        "primary_risk",
        "model_version",
        "feature_set_id",
    ):
        out[column] = out[column].astype(str).str.strip()
    if schema_version == WATCHLIST_SCHEMA_V2:
        out["strategy_policy_id"] = out["strategy_policy_id"].astype(str).str.strip()
    return out.sort_values(["sleeve", "rank", "symbol"], kind="stable").reset_index(drop=True)


def _receipt_date(receipt: Mapping[str, Any], field: str) -> str:
    return _date_key(receipt.get(field), field=f"receipt.{field}")


def _normalize_market_scope(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], frame.to_dict(orient="records"))


def _core_rows(frame: pd.DataFrame) -> list[tuple[str, str, int, float]]:
    return sorted(
        (
            str(row["symbol"]),
            str(row["sleeve"]),
            int(row["rank"]),
            round(float(row["tracking_weight"]), 10),
        )
        for row in _records(frame)
    )


__all__ = [
    "DEFAULT_WATCHLIST20_ROOT",
    "WATCHLIST_SCHEMA_V1",
    "WATCHLIST_SCHEMA_V2",
    "WATCHLIST_SCHEMAS",
    "RECEIPT_FILENAMES",
    "DATA_FILENAMES",
    "EXPECTED_TOTAL",
    "EXPECTED_SLEEVE_COUNTS",
    "WEIGHT_TOLERANCE",
    "THS_HOT_POLICY_SCHEMA",
    "THS_HOT_CLOSE_CUTOFF_MINUTE",
    "THS_HOT_MAX_SNAPSHOT_FALLBACK_MINUTES",
    "DailyWatch20ValidationError",
    "resolve_watchlist20_root",
    "_date_key",
    "_date_dash",
    "_load_json_mapping",
    "_resolve_existing",
    "_rows_from_json_payload",
    "_read_watchlist_frame",
    "_parse_weight",
    "_parse_bool",
    "_normalize_sleeve",
    "_require_columns",
    "_normalize_watchlist_frame",
    "_receipt_date",
    "_normalize_market_scope",
    "_sha256",
    "_records",
    "_core_rows",
]
