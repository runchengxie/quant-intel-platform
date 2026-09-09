from __future__ import annotations

from a_share_daily import morning_product_supervisor as supervisor


def test_d11_h5_research_shadow_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("MORNING_SUPERVISOR_D11_H5_ENABLED", raising=False)

    assert supervisor._d11_h5_enabled() is False


def test_d11_h5_research_shadow_can_be_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setenv("MORNING_SUPERVISOR_D11_H5_ENABLED", "1")

    assert supervisor._d11_h5_enabled() is True
