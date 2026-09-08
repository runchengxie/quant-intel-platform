"""Base helpers and shared constants for dashboard payload construction.

This module is the lowest layer of the payload package: it depends only on the
standard library and is imported by every other ``payload_*`` submodule. Keeping
shared numeric/JSON helpers and package-wide constants here avoids circular
imports between the higher-level builder modules.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

CHART_ROW_LIMIT = 756
NEIGHBOR_LIMIT = 12
USD_CNY_ASSUMPTION = 6.79

STATE_COLUMNS = (
    "own_risk_appetite_score",
    "rsp_spy_participation_proxy",
    "valuation_rate_gap_proxy",
    "vix",
)
CHART_COLUMNS = (
    "own_risk_appetite_score",
    "rsp_spy_participation_proxy",
    "valuation_rate_gap_proxy",
    "vix",
    "spy_close",
)
CHART_SERIES = (
    {"field": "own_risk_appetite_score", "label": "风险偏好", "color": "#2563eb"},
    {"field": "rsp_spy_participation_proxy", "label": "参与度", "color": "#0f766e"},
    {"field": "valuation_rate_gap_proxy", "label": "估值利率差", "color": "#7c3aed"},
    {"field": "vix", "label": "VIX", "color": "#b7791f"},
)
FORWARD_RETURN_COLUMNS = (
    ("spy_forward_return_fwd_90d", "3M"),
    ("spy_forward_return_fwd_252d", "1Y"),
    ("spy_forward_return_fwd_1260d", "5Y"),
    ("spy_forward_return_fwd_2520d", "10Y"),
)


@dataclass(frozen=True)
class JsonDocument:
    path: Path
    exists: bool
    data: dict[str, object]
    error: str | None = None


@dataclass(frozen=True)
class PanelDocument:
    path: Path | None
    exists: bool
    rows: list[dict[str, object]]
    error: str | None = None


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _load_json(path: Path) -> JsonDocument:
    if not path.exists():
        return JsonDocument(path=path, exists=False, data={})
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return JsonDocument(path=path, exists=True, data={}, error=str(exc))
    if not isinstance(raw, dict):
        return JsonDocument(path=path, exists=True, data={}, error="JSON root is not an object")
    return JsonDocument(path=path, exists=True, data=cast(dict[str, object], raw))


def _as_mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            number = float(stripped)
        except ValueError:
            return None
    else:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _rounded(value: object, digits: int = 2) -> float | None:
    number = _number(value)
    return round(number, digits) if number is not None else None


def _coerce_row_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        number = _number(stripped)
        return number if number is not None else stripped
    return value


def _first_present(*values: object) -> object | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _theme_valuation_average(scores: Mapping[str, Any]) -> float | None:
    values: list[float] = []
    for item in _as_list(scores.get("themes")):
        theme = _as_mapping(item)
        breakdown = _as_mapping(theme.get("breakdown"))
        value = _number(breakdown.get("valuation"))
        if value is not None:
            values.append(value)
    return round(sum(values) / len(values), 2) if values else None
