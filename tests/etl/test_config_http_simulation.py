from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from daily_messenger.etl import config, http, simulation


def test_config_helpers_normalize_keys_and_env_ai_news() -> None:
    payload = config.normalize_api_keys(
        {
            "alpha_vantage": "  av-key  ",
            "ai_feeds": [" https://example.com/feed.xml ", ""],
            "arxiv": {"max_results": 3, "throttle_seconds": 0.25},
        }
    )

    assert payload["alpha_vantage"] == "av-key"
    assert config.resolve_ai_feeds(payload) == ["https://example.com/feed.xml"]

    arxiv_params, throttle = config.resolve_arxiv_config(payload)
    assert arxiv_params["max_results"] == 3
    assert arxiv_params["sortBy"] == "submittedDate"
    assert throttle == 0.25

    config.merge_ai_news_env_config(
        payload,
        {
            "GLM_KEY_1": "glm-primary",
            "AI_NEWS_PROVIDER": "glm",
            "GLM_ENABLE_NETWORK": "0",
            "GLM_DIRECT_CONNECTION": "1",
            "GLM_TIMEOUT": "8",
            "ALIYUN_TIMEOUT": "35",
        },
    )
    ai_news = payload["ai_news"]
    assert ai_news["provider"] == "glm"
    assert ai_news["glm_enable_network"] is False
    assert ai_news["glm_direct_connection"] is True
    assert ai_news["glm_timeout"] == 8
    assert ai_news["aliyun_timeout"] == 35
    assert ai_news["keys"][0]["value"] == "glm-primary"


def test_config_rejects_invalid_canonical_key() -> None:
    with pytest.raises(config.ApiKeyValidationError) as exc_info:
        config.normalize_api_keys({"finnhub": 123})

    assert exc_info.value.errors == {"finnhub": "expected string value"}


def test_oanda_and_fred_environment_variables_override_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "api_keys.json"
    path.write_text(
        json.dumps({"fred": "json-fred", "oanda": "json-oanda"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("API_KEYS_PATH", str(path))
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("FRED_API_KEY", "env-fred")
    monkeypatch.setenv("OANDA_TOKEN", "env-oanda")
    monkeypatch.setenv("OANDA_API_TOKEN", "secondary-oanda")

    loaded = config.load_api_keys(None)

    assert loaded["fred"] == "env-fred"
    assert loaded["oanda"] == "env-oanda"


def test_resolve_api_key_uses_explicit_default_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "api_keys.json"
    path.write_text(json.dumps({"oanda": "json-oanda"}), encoding="utf-8")
    for name in (
        "API_KEYS",
        "API_KEYS_PATH",
        "OANDA",
        "OANDA_TOKEN",
        "OANDA_API_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    assert config.resolve_api_key("oanda", default_path=path) == "json-oanda"


def test_load_api_keys_falls_back_to_stable_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stable = tmp_path / ".config" / "market-intel"
    stable.mkdir(parents=True)
    (stable / "api_keys.json").write_text(
        json.dumps({"finnhub": "stable-finnhub"}), encoding="utf-8"
    )
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "release")
    monkeypatch.setattr(config.Path, "home", classmethod(lambda _cls: tmp_path))
    for name in ("API_KEYS", "API_KEYS_PATH", "FINNHUB"):
        monkeypatch.delenv(name, raising=False)

    assert config.load_api_keys(None)["finnhub"] == "stable-finnhub"


def test_http_request_json_retries_retryable_status(monkeypatch) -> None:
    class DummyResponse:
        def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
            self.status_code = status_code
            self._payload = payload
            self.headers = {"Retry-After": "0"}
            self.text = "body"

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status {self.status_code}")

        def json(self) -> dict[str, Any]:
            return self._payload

    class DummySession:
        def __init__(self) -> None:
            self.calls = 0
            self.trust_env = True

        def request(self, *args: Any, **kwargs: Any) -> DummyResponse:
            self.calls += 1
            if self.calls == 1:
                return DummyResponse(429, {})
            return DummyResponse(200, {"ok": True})

    sleeps: list[float] = []
    monkeypatch.setattr(http, "sleep_exact", sleeps.append)
    session = DummySession()

    payload = http.request_json(
        "https://example.com",
        session=session,  # type: ignore[arg-type]
        policy=http.RetryPolicy(retries=2),
        trust_env=False,
    )

    assert payload == {"ok": True}
    assert session.calls == 2
    assert session.trust_env is False
    assert sleeps == [0.0]


def test_simulation_outputs_are_deterministic() -> None:
    first_market, first_status = simulation.simulate_market_snapshot("2024-04-01")
    second_market, second_status = simulation.simulate_market_snapshot("2024-04-01")

    assert first_market == second_market
    assert first_status == second_status

    btc, btc_status = simulation.simulate_btc_theme("2024-04-01")
    events, events_status = simulation.simulate_events("2024-04-01")

    assert btc["date"] == "2024-04-01"
    assert btc_status.ok
    assert events[0]["date"] == "2024-04-01"
    assert events_status.ok
