"""Consumer validation for research-workspace weekly analysis artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.weekly_analysis.v1"
VALUE_ARTIFACT = "value_regime_weekly"
SIZE_ARTIFACT = "size_style_weekly"


def _date_key(value: object, *, field: str) -> str:
    text = str(value or "").strip().replace("-", "")
    try:
        return datetime.strptime(text, "%Y%m%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYYMMDD") from exc


def load_weekly_analysis_artifact(
    path: Path,
    *,
    artifact_type: str,
    expected_as_of: str | None = None,
) -> dict[str, Any]:
    """Load one validated research-owned weekly snapshot."""
    if artifact_type not in {VALUE_ARTIFACT, SIZE_ARTIFACT}:
        raise ValueError(f"unsupported weekly artifact type: {artifact_type}")
    if not path.is_file():
        raise ValueError(f"weekly analysis artifact is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read weekly analysis artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("weekly analysis artifact must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported weekly analysis schema")
    if payload.get("artifact_type") != artifact_type:
        raise ValueError("weekly analysis artifact type is invalid")
    as_of = _date_key(payload.get("as_of"), field="as_of")
    if expected_as_of is not None and as_of != _date_key(expected_as_of, field="expected_as_of"):
        raise ValueError(f"weekly artifact as_of={as_of} does not match expected {expected_as_of}")
    quality = payload.get("quality")
    if not isinstance(quality, dict) or quality.get("status") != "passed":
        raise ValueError("weekly analysis quality status is not passed")
    if not isinstance(payload.get("snapshot"), dict):
        raise ValueError("weekly analysis snapshot is missing")
    rows_key = "weekly_features" if artifact_type == VALUE_ARTIFACT else "series"
    rows = payload.get(rows_key)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"weekly analysis {rows_key} is empty")
    if quality.get("observation_count") != len(rows):
        raise ValueError("weekly analysis observation_count is inconsistent")
    return {**payload, "as_of": as_of}


__all__ = ["load_weekly_analysis_artifact"]
