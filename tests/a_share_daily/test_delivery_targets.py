from __future__ import annotations

import pytest

from a_share_daily.delivery.targets import resolve_delivery_targets


def test_resolve_delivery_targets_uses_public_audience_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_INTEL_CLIENT_CHAT_ID", "feishu:oc_client,oc_client")
    monkeypatch.setenv("MARKET_INTEL_INTERNAL_CHAT_ID", "oc_internal,oc_client")
    monkeypatch.setenv("MARKET_INTEL_DISABLED_CHAT_ID", "feishu:oc_internal")

    assert resolve_delivery_targets() == {
        "client": ("oc_client",),
        "internal": (),
    }
