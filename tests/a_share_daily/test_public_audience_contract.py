from __future__ import annotations

import pytest

from market_intel_config.audiences import resolve_audience_targets


def test_client_audience_uses_generic_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_INTEL_CLIENT_CHAT_ID", "oc_client")

    assert resolve_audience_targets("client") == ("oc_client",)


def test_client_audience_splits_and_deduplicates_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_INTEL_CLIENT_CHAT_ID", "feishu:oc_client,oc_client;oc_other")

    assert resolve_audience_targets("client") == ("oc_client", "oc_other")


def test_public_audience_has_no_default_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_INTEL_PUBLIC_CHAT_ID", raising=False)

    assert resolve_audience_targets("public") == ()


def test_unknown_audience_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown audience"):
        resolve_audience_targets("customer-name")  # type: ignore[arg-type]
