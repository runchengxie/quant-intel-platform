from __future__ import annotations

from dataclasses import dataclass

import pytest

from tushare_jobs.lightweight_snapshot import _init_pro


@dataclass
class FakeFrame:
    empty: bool


class FakeClient:
    def __init__(self, token: str, *, smoke_ok: bool) -> None:
        self.token = token
        self.smoke_ok = smoke_ok

    def trade_cal(self, **_kwargs: str) -> FakeFrame:
        if not self.smoke_ok:
            raise RuntimeError(f"connectivity failed for {self.token}")
        return FakeFrame(empty=False)


class FakeTushare:
    def __init__(self, smoke_results: dict[str, bool]) -> None:
        self.smoke_results = smoke_results
        self.pro_tokens: list[str] = []

    def set_token(self, _token: str) -> None:
        return None

    def pro_api(self, *, token: str) -> FakeClient:
        self.pro_tokens.append(token)
        return FakeClient(token, smoke_ok=self.smoke_results[token])


def test_lightweight_snapshot_falls_back_without_overwriting_primary() -> None:
    env = {
        "TUSHARE_TOKEN_2": "proxy-secret",
        "TUSHARE_API_URL_2": "https://proxy.example",
        "TUSHARE_TOKEN": "primary-secret",
    }
    original = dict(env)
    fake = FakeTushare({"proxy-secret": False, "primary-secret": True})

    client, label = _init_pro(env=env, tushare_module=fake)

    assert client.token == "primary-secret"
    assert label == "primary"
    assert fake.pro_tokens == ["proxy-secret", "primary-secret"]
    assert env == original


def test_lightweight_snapshot_uses_paired_proxy_first() -> None:
    fake = FakeTushare({"proxy-secret": True, "primary-secret": True})

    client, label = _init_pro(
        env={
            "TUSHARE_TOKEN_2": "proxy-secret",
            "TUSHARE_API_URL_2": "https://proxy.example",
            "TUSHARE_TOKEN": "primary-secret",
        },
        tushare_module=fake,
    )

    assert client.token == "proxy-secret"
    assert label == "proxy (https://proxy.example)"
    assert fake.pro_tokens == ["proxy-secret"]


def test_lightweight_snapshot_failure_does_not_expose_tokens() -> None:
    fake = FakeTushare({"proxy-secret": False, "primary-secret": False})

    with pytest.raises(SystemExit) as error:
        _init_pro(
            env={
                "TUSHARE_TOKEN_2": "proxy-secret",
                "TUSHARE_API_URL_2": "https://proxy.example",
                "TUSHARE_TOKEN": "primary-secret",
            },
            tushare_module=fake,
        )

    message = str(error.value)
    assert "TUSHARE_TOKEN_2" in message
    assert "TUSHARE_TOKEN" in message
    assert "proxy-secret" not in message
    assert "primary-secret" not in message
