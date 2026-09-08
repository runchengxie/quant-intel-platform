from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from daily_messenger.etl.fetchers import fred


class _Response:
    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        text: str = "",
        error: Exception | None = None,
    ) -> None:
        self._payload = payload
        self.text = text
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise ValueError("missing JSON")
        return self._payload


def _clear_fred_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("API_KEYS", "FRED", "FRED_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_fetch_observations_uses_json_fred_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "api_keys.json"
    registry.write_text(json.dumps({"fred": "json-fred"}), encoding="utf-8")
    monkeypatch.setenv("API_KEYS_PATH", str(registry))
    _clear_fred_environment(monkeypatch)
    calls: list[tuple[str, dict[str, str | int]]] = []

    def fake_get(url: str, *, params: dict[str, str | int], timeout: int) -> _Response:
        assert timeout == 7
        calls.append((url, params))
        return _Response(
            payload={
                "observations": [
                    {"date": "2026-07-14", "value": "4.10"},
                    {"date": "2026-07-15", "value": "4.20"},
                ]
            }
        )

    monkeypatch.setattr(fred.requests, "get", fake_get)

    observations = fred.fetch_observations("DGS10", limit=2, timeout=7)

    assert [(item.date, item.value) for item in observations] == [
        ("2026-07-14", 4.1),
        ("2026-07-15", 4.2),
    ]
    assert calls == [
        (
            fred.FRED_OBSERVATIONS_URL,
            {
                "series_id": "DGS10",
                "api_key": "json-fred",
                "file_type": "json",
                "sort_order": "desc",
                "limit": 2,
            },
        )
    ]


def test_fetch_observations_keeps_public_no_key_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEYS_PATH", str(tmp_path / "missing.json"))
    _clear_fred_environment(monkeypatch)
    calls: list[tuple[str, dict[str, str | int]]] = []

    def fake_get(url: str, *, params: dict[str, str | int], timeout: int) -> _Response:
        assert timeout == 9
        calls.append((url, params))
        return _Response(text="observation_date,VIXCLS\n2026-07-14,18.0\n2026-07-15,17.5\n")

    monkeypatch.setattr(fred.requests, "get", fake_get)

    observations = fred.fetch_observations("VIXCLS", limit=2, timeout=9)

    assert [(item.date, item.value) for item in observations] == [
        ("2026-07-14", 18.0),
        ("2026-07-15", 17.5),
    ]
    assert calls == [(fred.FRED_GRAPH_URL, {"id": "VIXCLS"})]


def test_authenticated_failure_falls_back_without_disclosing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "api_keys.json"
    registry.write_text(json.dumps({"fred": "synthetic-secret"}), encoding="utf-8")
    monkeypatch.setenv("API_KEYS_PATH", str(registry))
    _clear_fred_environment(monkeypatch)
    calls: list[str] = []

    def fake_get(url: str, *, params: dict[str, str | int], timeout: int) -> _Response:
        del params, timeout
        calls.append(url)
        if url == fred.FRED_OBSERVATIONS_URL:
            return _Response(error=requests.HTTPError("synthetic-secret"))
        return _Response(text="observation_date,DGS10\n2026-07-15,4.20\n")

    monkeypatch.setattr(fred.requests, "get", fake_get)

    observations = fred.fetch_observations("DGS10", timeout=5)

    assert observations == [fred.FredObservation(date="2026-07-15", value=4.2)]
    assert calls == [fred.FRED_OBSERVATIONS_URL, fred.FRED_GRAPH_URL]
