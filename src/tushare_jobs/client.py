"""TuShare credential resolution and client initialisation helpers.

The higher-permission proxy account is the default production route.  The
primary account is deliberately retained as a fallback candidate, rather than
being overwritten in ``os.environ`` while trying the proxy account.  Returning
an ordered credential chain does not authorize request-level replay.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import tushare as ts


@dataclass(frozen=True)
class TushareCredential:
    """A resolved credential without a secret-bearing representation."""

    token_env: str
    token: str = field(repr=False)
    api_url: str | None = None

    @property
    def label(self) -> str:
        return "proxy" if self.token_env == "TUSHARE_TOKEN_2" else "primary"


def resolve_tushare_credentials(
    token: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[TushareCredential, ...]:
    """Return the ordered TuShare credential chain.

    Resolution is intentionally strict for ``TUSHARE_TOKEN_2``: it is only
    usable together with ``TUSHARE_API_URL_2``.  This prevents a proxy-scoped
    token from being silently sent to the primary endpoint.  ``TUSHARE_TOKEN``
    is the only eligible fallback candidate; callers must explicitly decide
    whether retrying a request with it is safe.
    """

    values = os.environ if env is None else env
    explicit = str(token or "").strip()
    if explicit:
        return (
            TushareCredential(
                token_env="explicit",
                token=explicit,
                api_url=str(values.get("TUSHARE_API_URL") or "").strip() or None,
            ),
        )

    proxy_token = str(values.get("TUSHARE_TOKEN_2") or "").strip()
    proxy_url = str(values.get("TUSHARE_API_URL_2") or "").strip()
    primary_token = str(values.get("TUSHARE_TOKEN") or "").strip()
    primary_url = str(values.get("TUSHARE_API_URL") or "").strip() or None

    credentials: list[TushareCredential] = []
    if proxy_token and proxy_url:
        credentials.append(
            TushareCredential(
                token_env="TUSHARE_TOKEN_2",
                token=proxy_token,
                api_url=proxy_url,
            )
        )
    if primary_token and primary_token != proxy_token:
        credentials.append(
            TushareCredential(
                token_env="TUSHARE_TOKEN",
                token=primary_token,
                api_url=primary_url,
            )
        )

    if credentials:
        return tuple(credentials)
    if proxy_token and not proxy_url:
        raise SystemExit(
            "TUSHARE_TOKEN_2 is set but TUSHARE_API_URL_2 is missing; "
            "configure the matching proxy URL or provide TUSHARE_TOKEN as fallback."
        )
    raise SystemExit(
        "Missing TuShare token. Set TUSHARE_TOKEN_2 with TUSHARE_API_URL_2, "
        "or set fallback TUSHARE_TOKEN."
    )


def create_tushare_client(
    credential: TushareCredential,
    *,
    tushare_module: Any = ts,
) -> Any:
    """Create one client without mutating process credential variables."""

    tushare_module.set_token(credential.token)
    client = tushare_module.pro_api(token=credential.token)
    if credential.api_url:
        client._DataApi__http_url = credential.api_url
    return client


def init_tushare(
    token: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
    tushare_module: Any = ts,
) -> Any:
    """Return a configured TuShare pro_api client.

    Token resolution order:
    1. Explicit `token` argument.
    2. ``TUSHARE_TOKEN_2`` with matching ``TUSHARE_API_URL_2``.
    3. ``TUSHARE_TOKEN`` fallback.

    Client construction is retried with the fallback credential when the
    proxy client cannot be created.  Request-level fallback remains the
    caller's responsibility because requests may not be idempotent.
    """

    failed_envs: list[str] = []
    for credential in resolve_tushare_credentials(token, env=env):
        try:
            return create_tushare_client(credential, tushare_module=tushare_module)
        except Exception:  # noqa: BLE001 - retry without exposing provider errors or tokens
            failed_envs.append(credential.token_env)
    raise RuntimeError(
        "Unable to initialize a TuShare client from configured credential envs: "
        + ", ".join(failed_envs)
    )


__all__ = [
    "TushareCredential",
    "create_tushare_client",
    "init_tushare",
    "resolve_tushare_credentials",
]
