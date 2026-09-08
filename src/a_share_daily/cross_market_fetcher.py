"""Fetcher 抽象：解耦 cross_market 对 daily_messenger.etl.fetchers.fred 的具体依赖。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Fetcher(Protocol):
    def fetch_observations(
        self,
        series_id: str,
        *,
        start: str,
        limit: int,
        timeout: int,
    ) -> list: ...


class FredAdapter:
    """惰性包装 daily_messenger.etl.fetchers.fred。"""

    def fetch_observations(
        self,
        series_id: str,
        *,
        start: str,
        limit: int,
        timeout: int,
    ) -> list:
        from daily_messenger.etl.fetchers import fred  # 惰性，消除模块级硬反向 import

        return fred.fetch_observations(series_id, start=start, limit=limit, timeout=timeout)
