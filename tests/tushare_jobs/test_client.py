from __future__ import annotations

from dataclasses import dataclass

import pytest

from tushare_jobs.client import init_tushare, resolve_tushare_credentials


@dataclass
class FakeClient:
    token: str


class FakeTushare:
    def __init__(self, *, fail_tokens: set[str] | None = None) -> None:
        self.fail_tokens = fail_tokens or set()
        self.set_tokens: list[str] = []
        self.pro_tokens: list[str] = []

    def set_token(self, token: str) -> None:
        self.set_tokens.append(token)

    def pro_api(self, *, token: str) -> FakeClient:
        self.pro_tokens.append(token)
        if token in self.fail_tokens:
            raise RuntimeError(f"provider rejected {token}")
        return FakeClient(token=token)


def test_resolve_credentials_prefers_paired_proxy_then_primary() -> None:
    credentials = resolve_tushare_credentials(
        env={
            "TUSHARE_TOKEN_2": "proxy-secret",
            "TUSHARE_API_URL_2": "https://proxy.example",
            "TUSHARE_TOKEN": "primary-secret",
            "TUSHARE_API_URL": "https://api.example",
        }
    )

    assert [item.token_env for item in credentials] == ["TUSHARE_TOKEN_2", "TUSHARE_TOKEN"]
    assert [item.api_url for item in credentials] == [
        "https://proxy.example",
        "https://api.example",
    ]
    assert "proxy-secret" not in repr(credentials[0])
    assert "primary-secret" not in repr(credentials[1])


def test_unpaired_proxy_is_skipped_when_primary_fallback_exists() -> None:
    credentials = resolve_tushare_credentials(
        env={
            "TUSHARE_TOKEN_2": "proxy-secret",
            "TUSHARE_TOKEN": "primary-secret",
        }
    )

    assert [item.token_env for item in credentials] == ["TUSHARE_TOKEN"]


def test_unpaired_proxy_without_primary_fails_closed() -> None:
    with pytest.raises(SystemExit, match="TUSHARE_API_URL_2") as error:
        resolve_tushare_credentials(env={"TUSHARE_TOKEN_2": "proxy-secret"})

    assert "proxy-secret" not in str(error.value)


def test_init_tushare_retries_primary_when_proxy_client_creation_fails() -> None:
    fake = FakeTushare(fail_tokens={"proxy-secret"})
    client = init_tushare(
        env={
            "TUSHARE_TOKEN_2": "proxy-secret",
            "TUSHARE_API_URL_2": "https://proxy.example",
            "TUSHARE_TOKEN": "primary-secret",
        },
        tushare_module=fake,
    )

    assert client.token == "primary-secret"
    assert fake.pro_tokens == ["proxy-secret", "primary-secret"]


def test_init_tushare_applies_proxy_url_without_using_primary() -> None:
    fake = FakeTushare()
    client = init_tushare(
        env={
            "TUSHARE_TOKEN_2": "proxy-secret",
            "TUSHARE_API_URL_2": "https://proxy.example",
            "TUSHARE_TOKEN": "primary-secret",
        },
        tushare_module=fake,
    )

    assert client.token == "proxy-secret"
    assert client._DataApi__http_url == "https://proxy.example"
    assert fake.pro_tokens == ["proxy-secret"]
