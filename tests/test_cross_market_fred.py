"""护盾测试：cross_market 的 FRED 数据路径。

全部使用 fake，无网络、快速。
- _fred_csv 通过 fetcher= 参数注入测试；
- _fetch_macros / _fetch_cboe 内部调 _fred_csv() 不传 fetcher，故 monkeypatch
  FredAdapter.fetch_observations 以隔离真实 fred 模块（避免网络 + 验证解耦）。
"""

from __future__ import annotations

import pytest

from a_share_daily import cross_market
from a_share_daily.cross_market_fetcher import FredAdapter


class _FakeObs:
    """observation-like 对象，兼容 .value / .date 访问。"""

    def __init__(self, date: str, value: float) -> None:
        self.date = date
        self.value = value


class _FakeFredFetcher:
    """实现 Fetcher 协议的 fake，返回可控 observation 列表。"""

    def __init__(self, observations: list[_FakeObs]) -> None:
        self._observations = observations

    def fetch_observations(
        self,
        series_id: str,
        *,
        start: str,
        limit: int,
        timeout: int,
    ) -> list[_FakeObs]:
        obs = self._observations
        if limit is not None:
            obs = obs[-limit:]
        return obs


@pytest.fixture
def fake_fetcher() -> _FakeFredFetcher:
    return _FakeFredFetcher(
        [
            _FakeObs(date="2026-06-29", value=17.5),
            _FakeObs(date="2026-06-30", value=18.2),
        ]
    )


@pytest.fixture
def patched_fred(monkeypatch: pytest.MonkeyPatch) -> None:
    """monkeypatch FredAdapter.fetch_observations，使默认路径无网络。"""

    def fake_fetch(
        self: FredAdapter,
        series_id: str,
        *,
        start: str,
        limit: int,
        timeout: int,
    ) -> list[_FakeObs]:
        return [
            _FakeObs(date="2026-06-29", value=17.5),
            _FakeObs(date="2026-06-30", value=18.2),
        ]

    monkeypatch.setattr(FredAdapter, "fetch_observations", fake_fetch)


# ── _fred_csv 直接测试（fetcher 参数注入）─────────────────────


def test_fred_csv_returns_latest_previous_date(fake_fetcher: _FakeFredFetcher) -> None:
    latest, previous, as_of = cross_market._fred_csv("VIXCLS", fetcher=fake_fetcher)
    assert latest == 18.2
    assert previous == 17.5
    assert as_of == "2026-06-30"


def test_fred_csv_raises_when_fewer_than_two(fake_fetcher: _FakeFredFetcher) -> None:
    fake_fetcher._observations = [_FakeObs(date="2026-06-30", value=18.2)]
    with pytest.raises(RuntimeError):
        cross_market._fred_csv("VIXCLS", fetcher=fake_fetcher)


# ── 端点函数测试（默认 FredAdapter 路径，monkeypatch 隔离网络）──


def test_fetch_macros_contains_fred_source(patched_fred: None) -> None:
    macros = cross_market._fetch_macros()
    # ^TNX (DGS10) 仅走 FRED 路径，应含 source: "fred"
    assert "^TNX" in macros
    assert macros["^TNX"]["source"] == "fred"
    # 整体结构应完整返回（FRED/CBOE/yfinance 各分支均不崩）
    for sym in ("^VIX", "^VVIX", "^TNX", "DX-Y.NYB"):
        assert sym in macros


def test_fetch_cboe_contains_fred_vixcls(patched_fred: None) -> None:
    cboe = cross_market._fetch_cboe()
    assert cboe is not None
    assert cboe["source"] == "fred_vixcls"
    assert cboe["vix"] == 18.2
