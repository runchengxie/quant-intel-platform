"""FRED observations with optional authenticated API access and public fallback."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests

from daily_messenger.etl.config import resolve_api_key

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_API_KEYS_PATH = PROJECT_ROOT / "api_keys.json"
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FredFetchError(RuntimeError):
    """Raised when neither configured FRED source can produce observations."""


@dataclass(frozen=True)
class FredObservation:
    date: str
    value: float


def _coerce_observation(raw_date: Any, raw_value: Any) -> FredObservation | None:
    date_text = str(raw_date or "").strip()
    value_text = str(raw_value or "").strip()
    if not date_text or not value_text or value_text == ".":
        return None
    try:
        date.fromisoformat(date_text)
        value = float(value_text)
    except (TypeError, ValueError):
        return None
    return FredObservation(date=date_text, value=value)


def _authenticated_observations(
    series_id: str,
    api_key: str,
    *,
    start: str | None,
    limit: int | None,
    timeout: int,
) -> list[FredObservation]:
    params: dict[str, str | int] = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc" if limit is not None else "asc",
    }
    if start:
        params["observation_start"] = start
    if limit is not None:
        params["limit"] = limit
    try:
        response = requests.get(FRED_OBSERVATIONS_URL, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, TypeError, ValueError):
        raise FredFetchError(f"FRED authenticated fetch failed for {series_id}") from None
    rows = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise FredFetchError(f"FRED authenticated response was invalid for {series_id}")
    observations = [
        observation
        for row in rows
        if isinstance(row, dict)
        and (observation := _coerce_observation(row.get("date"), row.get("value"))) is not None
    ]
    observations.sort(key=lambda item: item.date)
    if not observations:
        raise FredFetchError(f"FRED authenticated response was empty for {series_id}")
    return observations


def _public_csv_observations(
    series_id: str,
    *,
    start: str | None,
    limit: int | None,
    timeout: int,
) -> list[FredObservation]:
    params: dict[str, str] = {"id": series_id}
    if start:
        params["cosd"] = start
    try:
        response = requests.get(FRED_GRAPH_URL, params=params, timeout=timeout)
        response.raise_for_status()
        rows = csv.DictReader(io.StringIO(response.text))
        observations = [
            observation
            for row in rows
            if (observation := _coerce_observation(row.get("observation_date"), row.get(series_id)))
            is not None
        ]
    except (csv.Error, requests.RequestException, TypeError, ValueError):
        raise FredFetchError(f"FRED public fetch failed for {series_id}") from None
    observations.sort(key=lambda item: item.date)
    if limit is not None:
        observations = observations[-limit:]
    if not observations:
        raise FredFetchError(f"FRED public response was empty for {series_id}")
    return observations


def fetch_observations(
    series_id: str,
    *,
    start: str | None = None,
    limit: int | None = None,
    timeout: int = 20,
) -> list[FredObservation]:
    """Fetch observations, preferring a configured key and retaining no-key access.

    ``FRED_API_KEY`` overrides the ``fred`` entry in ``api_keys.json`` through the
    shared configuration loader. An authenticated failure falls back to FRED's
    public graph CSV endpoint, which does not require a key.
    """

    api_key = resolve_api_key("fred", default_path=DEFAULT_API_KEYS_PATH)
    if api_key:
        try:
            return _authenticated_observations(
                series_id,
                api_key,
                start=start,
                limit=limit,
                timeout=timeout,
            )
        except FredFetchError:
            pass
    return _public_csv_observations(series_id, start=start, limit=limit, timeout=timeout)


__all__ = ["FredFetchError", "FredObservation", "fetch_observations"]
