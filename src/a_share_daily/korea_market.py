"""韩国市场数据的可选 provider 与 A 股盘前信号。

KRX Open API 并不是运行本模块的前置条件。没有 API key 时，优先使用
FinanceDataReader，再使用 pykrx，最后回退到 yfinance。所有替代源都会
标记为 ``degraded=True``，避免把代理数据误报成官方实时数据。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from importlib import import_module
from typing import Any

from .global_leadlag import GLOBAL_LEAD_LAG_INSTRUMENTS

KOREA_SYMBOLS = tuple(
    instrument.symbol for instrument in GLOBAL_LEAD_LAG_INSTRUMENTS if instrument.market == "KR"
)
KOREA_INDEX_SYMBOL = "^KS11"
_KOREA_CONCEPTS = {
    instrument.symbol: instrument.concepts
    for instrument in GLOBAL_LEAD_LAG_INSTRUMENTS
    if instrument.market == "KR"
}
logger = logging.getLogger(__name__)


def _load_optional(name: str) -> Any | None:
    try:
        return import_module(name)
    except (ImportError, ModuleNotFoundError):
        return None


def _close_values(frame: Any, columns: tuple[str, ...]) -> list[float]:
    for column in columns:
        try:
            values = frame[column].dropna().tolist()
        except (KeyError, AttributeError, TypeError):
            continue
        if len(values) >= 2:
            return [float(values[-2]), float(values[-1])]
    return []


def _quote(previous: float, latest: float, source: str) -> dict[str, Any]:
    pct = (latest - previous) / previous * 100 if previous else 0.0
    return {
        "close": round(latest, 4),
        "pct_chg": round(pct, 2),
        "source": source,
        "degraded": True,
    }


def _fetch_from_fdr(module: Any, symbol: str, start: str, end: str) -> list[float]:
    try:
        return _close_values(module.DataReader(symbol, start, end), ("Close", "종가"))
    except Exception as exc:
        logger.debug("FinanceDataReader failed for %s: %s", symbol, exc)
        return []


def _fetch_from_pykrx(module: Any, ticker: str, start: str, end: str) -> list[float]:
    try:
        frame = module.stock.get_market_ohlcv(start, end, ticker)
        return _close_values(frame, ("종가", "Close"))
    except Exception as exc:
        logger.debug("pykrx failed for %s: %s", ticker, exc)
        return []


def _fetch_from_yfinance(module: Any, symbol: str, start: str, end: str) -> list[float]:
    try:
        frame = module.download(
            symbol,
            start=start,
            end=(date.fromisoformat(end) + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=False,
        )
        return _close_values(frame, ("Close",))
    except Exception as exc:
        logger.debug("yfinance failed for %s: %s", symbol, exc)
        return []


def fetch_korea_daily_quotes(
    symbols: list[str] | tuple[str, ...],
    start: str,
    end: str,
    *,
    fdr_module: Any = ...,
    pykrx_module: Any = ...,
    yfinance_module: Any = ...,
) -> dict[str, dict[str, Any]]:
    """Fetch daily Korea quotes without requiring an API key.

    Module arguments are dependency-injection hooks for tests and allow
    deployments to disable a provider with ``None``.
    """
    if fdr_module is ...:
        fdr_module = _load_optional("FinanceDataReader")
    if pykrx_module is ...:
        pykrx_module = _load_optional("pykrx")
    if yfinance_module is ...:
        yfinance_module = _load_optional("yfinance")

    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        ticker = symbol.removesuffix(".KS")

        if fdr_module is not None:
            values = _fetch_from_fdr(fdr_module, symbol, start, end)
            if values:
                result[symbol] = _quote(values[0], values[1], "finance-datareader")
                continue

        if pykrx_module is not None:
            values = _fetch_from_pykrx(
                pykrx_module,
                ticker,
                start.replace("-", ""),
                end.replace("-", ""),
            )
            if values:
                result[symbol] = _quote(values[0], values[1], "pykrx")
                continue

        if yfinance_module is not None:
            values = _fetch_from_yfinance(yfinance_module, symbol, start, end)
            if values:
                result[symbol] = _quote(values[0], values[1], "yfinance")

    return result


def compute_korea_signal(
    quotes: dict[str, dict[str, Any]],
    *,
    window: str,
) -> dict[str, Any]:
    """Summarize Korea's sector move as an A-share pre-open warning signal."""
    instruments = [quotes[symbol] for symbol in KOREA_SYMBOLS if symbol in quotes]
    valid = [item for item in instruments if isinstance(item.get("pct_chg"), (int, float))]
    if not valid:
        return {
            "window": window,
            "signal": "neutral",
            "risk_level": "unknown",
            "avg_pct_chg": 0.0,
            "residual_pct_chg": 0.0,
            "concepts": [],
            "drivers": [],
            "source": "unavailable",
            "degraded": True,
        }

    average = sum(float(item["pct_chg"]) for item in valid) / len(valid)
    market_move = float(quotes.get(KOREA_INDEX_SYMBOL, {}).get("pct_chg", 0.0) or 0.0)
    residual = average - market_move
    direction = "bullish" if residual > 1 else "bearish" if residual < -1 else "neutral"
    risk_level = "high" if abs(residual) >= 2 else "medium" if abs(residual) >= 1 else "low"
    concepts = sorted(
        {
            concept
            for symbol in KOREA_SYMBOLS
            if symbol in quotes and isinstance(quotes[symbol].get("pct_chg"), (int, float))
            for concept in _KOREA_CONCEPTS.get(symbol, ())
        }
    )
    drivers = [
        f"{symbol} {float(quotes[symbol]['pct_chg']):+.1f}%"
        for symbol in KOREA_SYMBOLS
        if symbol in quotes and isinstance(quotes[symbol].get("pct_chg"), (int, float))
    ]
    sources = {str(item.get("source", "unknown")) for item in valid}
    source = next(iter(sources)) if len(sources) == 1 else "mixed"
    if source != "krx":
        source = "daily-proxy"
    return {
        "window": window,
        "signal": direction,
        "risk_level": risk_level,
        "avg_pct_chg": round(average, 2),
        "residual_pct_chg": round(residual, 2),
        "market_pct_chg": round(market_move, 2),
        "concepts": concepts,
        "drivers": drivers,
        "source": source,
        "degraded": source == "daily-proxy",
    }
