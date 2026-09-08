"""港股行情抓取（hk 组）。

从 daily_messenger.etl.run_fetch 拆出的港股组，覆盖恒生指数（^HSI）的
Stooq / Yahoo 双来源抓取与代理回退。底层行情辅助函数复用 etl.fetchers.quotes，
是否允许 Yahoo 回退复用共享的 _yahoo_allowed。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from daily_messenger.etl.fetchers._common import _yahoo_allowed
from daily_messenger.etl.fetchers.quotes import (
    _extract_latest_change,
    _extract_yahoo_change,
    _fetch_stooq_series,
    _fetch_yahoo_chart,
)
from daily_messenger.etl.types import FetchStatus

logger = logging.getLogger(__name__)

HK_MARKET_SYMBOLS = [
    {"symbol": "HSI", "label": "HSI"},
]

HK_PROXY_SYMBOLS = [
    "2800.HK",
    "2828.HK",
]


def _fetch_hsi_from_stooq() -> tuple[list[dict[str, Any]], str]:
    rows = _fetch_stooq_series("^hsi")
    day, close, change_pct = _extract_latest_change(rows)
    payload = [
        {
            "symbol": HK_MARKET_SYMBOLS[0]["label"],
            "close": round(close, 2),
            "change_pct": round(change_pct, 2),
        }
    ]
    message = f"使用 Stooq (^HSI) 数据（{day}）"
    return payload, message


def _fetch_hsi_from_yahoo() -> tuple[list[dict[str, Any]], str]:
    chart = _fetch_yahoo_chart("^HSI")
    day, close, change_pct = _extract_yahoo_change(chart)
    payload = [
        {
            "symbol": HK_MARKET_SYMBOLS[0]["label"],
            "close": round(close, 2),
            "change_pct": round(change_pct, 2),
        }
    ]
    message = f"使用 Yahoo Finance ^HSI 数据（{day}）"
    return payload, message


def _fetch_hk_proxy_from_yahoo(symbol: str) -> tuple[list[dict[str, Any]], str]:
    chart = _fetch_yahoo_chart(symbol)
    day, close, change_pct = _extract_yahoo_change(chart)
    payload = [
        {
            "symbol": HK_MARKET_SYMBOLS[0]["label"],
            "close": round(close, 2),
            "change_pct": round(change_pct, 2),
        }
    ]
    message = f"使用 Yahoo Finance {symbol} 代理（{day}）"
    return payload, message


def _fetch_hk_market_snapshot(
    api_keys: dict[str, Any],
) -> tuple[list[dict[str, Any]], FetchStatus]:
    errors: list[str] = []

    fetchers: list[Callable[[], tuple[list[dict[str, Any]], str]]] = [_fetch_hsi_from_stooq]
    if _yahoo_allowed():
        fetchers.append(_fetch_hsi_from_yahoo)

    for fetcher in fetchers:
        try:
            rows, message = fetcher()
            return rows, FetchStatus(name="hongkong_HSI", ok=True, message=message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_hk_market_snapshot" + " 捕获到异常", exc_info=True)
            fetcher_name = getattr(fetcher, "__name__", repr(fetcher))
            errors.append(f"{fetcher_name}: {exc}")

    if _yahoo_allowed():
        for proxy in HK_PROXY_SYMBOLS:
            try:
                rows, message = _fetch_hk_proxy_from_yahoo(proxy)
                return rows, FetchStatus(name="hongkong_HSI", ok=True, message=message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("_fetch_hk_market_snapshot" + " 捕获到异常", exc_info=True)
                errors.append(f"{proxy}: {exc}")

    detail = "; ".join(errors) if errors else "未知原因"
    return [], FetchStatus(name="hongkong_HSI", ok=False, message=f"港股行情获取失败: {detail}")
