"""行情源抓取（quote-source 组）。

从 daily_messenger.etl.run_fetch 拆出的行情源组，覆盖 stooq / yahoo /
fmp / twelve_data / alpaca / alpha 六个来源，并提供 Yahoo 批量报价接口。
共享的底层抓取与解析辅助函数（_fetch_yahoo_chart、_fetch_stooq_series 等）
也放在本模块，供港股组（etl.fetchers.hk）复用，避免重复实现。
"""

from __future__ import annotations

import csv
import logging
import os
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import requests

from daily_messenger.etl.config import (
    coerce_api_key as _coerce_api_key,
)
from daily_messenger.etl.fetchers._common import (
    BROWSER_USER_AGENT,
    _safe_float,
    _yahoo_allowed,
)
from daily_messenger.etl.http import (
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from daily_messenger.etl.http import (
    request_json as _request_json,
)
from daily_messenger.etl.types import QuoteSnapshot as _QuoteSnapshot

logger = logging.getLogger(__name__)

THROTTLE_DISABLED = os.getenv("DM_DISABLE_THROTTLE", "").lower() in {"1", "true", "yes"}


def _sleep(seconds: float) -> None:
    if seconds <= 0 or THROTTLE_DISABLED:
        return
    time.sleep(seconds)


def _fetch_alpha_series(symbol: str, api_key: str) -> dict[str, Any]:
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": api_key,
    }
    payload = _request_json(url, params=params)
    key = next((k for k in payload if "Time Series" in k), None)
    if not key:
        message = (
            payload.get("Information") or payload.get("Note") or "Alpha Vantage 未返回时间序列"
        )
        raise RuntimeError(message)
    return payload[key]


def _extract_close_change(
    series: dict[str, dict[str, str]],
) -> tuple[str, float, float]:
    dates = sorted(series.keys(), reverse=True)
    if len(dates) < 2:
        raise RuntimeError("时间序列不足以计算涨跌幅")
    latest, prev = dates[0], dates[1]
    close = float(series[latest]["4. close"])
    prev_close = float(series[prev]["4. close"])
    change_pct = (close - prev_close) / prev_close * 100
    return latest, close, change_pct


def _stooq_symbol_candidates(symbol: str) -> list[str]:
    base = symbol.lower()
    candidates = [base]
    if "." not in base and not base.startswith("^"):
        candidates.append(f"{base}.us")
    return list(dict.fromkeys(candidates))


def _fetch_stooq_series(symbol: str) -> list[dict[str, Any]]:
    params = {"s": symbol.lower(), "i": "d"}
    resp = requests.get(
        "https://stooq.com/q/d/l/",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    reader = csv.DictReader(resp.text.splitlines())
    rows: list[dict[str, Any]] = []
    for row in reader:
        normalized = {
            k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k
        }
        if normalized.get("date"):
            rows.append(normalized)
    if len(rows) < 2:
        raise RuntimeError("Stooq 未返回足够的时间序列")
    return rows


def _extract_latest_change(
    rows: list[dict[str, Any]], *, close_key: str = "close"
) -> tuple[str, float, float]:
    ordered = sorted(rows, key=lambda item: item.get("date"))
    latest, prev = ordered[-1], ordered[-2]
    latest_close = _safe_float(latest.get(close_key))
    prev_close = _safe_float(prev.get(close_key))
    if latest_close is None or prev_close is None or prev_close == 0:
        raise RuntimeError("无法计算涨跌幅")
    change_pct = (latest_close - prev_close) / prev_close * 100
    return str(latest.get("date", "")), latest_close, change_pct


def _fetch_yahoo_chart(symbol: str) -> dict[str, Any]:
    encoded = quote(symbol, safe="")
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{encoded}"
    params = {"interval": "1d", "range": "5d"}
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://finance.yahoo.com/",
    }
    payload = _request_json(url, params=params, headers=headers)
    chart = (payload.get("chart") or {}).get("result") or []
    if not chart:
        raise RuntimeError("Yahoo Finance 未返回行情")
    return chart[0]


def _extract_yahoo_change(chart: dict[str, Any]) -> tuple[str, float, float]:
    timestamps = chart.get("timestamp") or []
    quotes = (chart.get("indicators") or {}).get("quote") or []
    if not timestamps or not quotes:
        raise RuntimeError("Yahoo Finance 响应缺少时间序列")
    closes = quotes[0].get("close") or []
    pairs = [
        (ts, close) for ts, close in zip(timestamps, closes, strict=False) if close is not None
    ]
    if len(pairs) < 2:
        raise RuntimeError("Yahoo Finance 未返回足够的收盘价")
    pairs.sort(key=lambda item: item[0])
    _prev_ts, prev_close = pairs[-2]
    latest_ts, latest_close = pairs[-1]
    if not prev_close:
        raise RuntimeError("Yahoo Finance 前一日收盘价无效")
    change_pct = (latest_close - prev_close) / prev_close * 100
    day = datetime.fromtimestamp(latest_ts, UTC).date().isoformat()
    return day, latest_close, change_pct


def _attempt_quote(
    fetchers: Iterable[tuple[str, Callable[[], _QuoteSnapshot]]],
) -> _QuoteSnapshot:
    errors: list[str] = []
    for label, fetcher in fetchers:
        try:
            return fetcher()
        except Exception as exc:  # noqa: BLE001
            logger.warning("_attempt_quote" + " 捕获到异常", exc_info=True)
            errors.append(f"{label}: {exc}")
    detail = "; ".join(errors) if errors else "无可用行情来源"
    raise RuntimeError(detail)


def _fetch_quote_from_stooq(symbol: str) -> _QuoteSnapshot:
    errors: list[str] = []
    for candidate in _stooq_symbol_candidates(symbol):
        try:
            rows = _fetch_stooq_series(candidate)
            day, close, change_pct = _extract_latest_change(rows)
            return _QuoteSnapshot(
                day=day,
                close=round(close, 4),
                change_pct=round(change_pct, 4),
                source=f"stooq:{candidate}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_quote_from_stooq" + " 捕获到异常", exc_info=True)
            errors.append(f"{candidate}: {exc}")
    detail = "; ".join(errors) if errors else "Stooq 未返回数据"
    raise RuntimeError(detail)


def _fetch_quote_from_yahoo(symbol: str) -> _QuoteSnapshot:
    chart = _fetch_yahoo_chart(symbol)
    day, close, change_pct = _extract_yahoo_change(chart)
    return _QuoteSnapshot(
        day=day,
        close=round(close, 4),
        change_pct=round(change_pct, 4),
        source=f"yahoo:{symbol}",
    )


def _fetch_quote_from_fmp(symbol: str, api_key: str) -> _QuoteSnapshot:
    url = "https://financialmodelingprep.com/stable/historical-price-eod/full"
    params = {"symbol": symbol, "apikey": api_key}
    payload = _request_json(url, params=params)
    if isinstance(payload, dict):
        history = payload.get("historical") or payload.get("data") or []
    else:
        history = payload if isinstance(payload, list) else []
    if len(history) < 2:
        raise RuntimeError("FMP 未返回足够的历史数据")
    ordered = sorted(history, key=lambda item: item.get("date"), reverse=True)
    latest, prev = ordered[0], ordered[1]
    day = latest.get("date")
    close = _safe_float(latest.get("close"))
    prev_close = _safe_float(prev.get("close"))
    if not day or close is None or prev_close in (None, 0):
        raise RuntimeError("FMP 历史数据缺字段")
    change_pct = (close - prev_close) / prev_close * 100
    return _QuoteSnapshot(
        day=day, close=round(close, 4), change_pct=round(change_pct, 4), source="fmp"
    )


def _fetch_quote_from_twelve_data(symbol: str, api_key: str) -> _QuoteSnapshot:
    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": 2,
        "apikey": api_key,
    }
    payload = _request_json("https://api.twelvedata.com/time_series", params=params)
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise RuntimeError(payload.get("message") or "Twelve Data 返回错误")
    values = payload.get("values") if isinstance(payload, dict) else None
    if not values or len(values) < 2:
        raise RuntimeError("Twelve Data 未返回足够的时间序列")
    ordered = sorted(values, key=lambda item: item.get("datetime"), reverse=True)
    latest, prev = ordered[0], ordered[1]
    day = latest.get("datetime")
    close = _safe_float(latest.get("close"))
    prev_close = _safe_float(prev.get("close"))
    if not day or close is None or prev_close in (None, 0):
        raise RuntimeError("Twelve Data 时间序列缺字段")
    change_pct = (close - prev_close) / prev_close * 100
    normalized_day = day.split(" ")[0] if isinstance(day, str) else str(day)
    return _QuoteSnapshot(
        day=normalized_day,
        close=round(close, 4),
        change_pct=round(change_pct, 4),
        source="twelve_data",
    )


def _fetch_quote_from_alpaca(symbol: str, key_id: str, secret: str) -> _QuoteSnapshot:
    params = {
        "symbols": symbol,
        "timeframe": "1Day",
        "limit": 2,
        "adjustment": "raw",
    }
    headers = {
        "APCA-API-KEY-ID": key_id,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }
    payload = _request_json(
        "https://data.alpaca.markets/v2/stocks/bars", params=params, headers=headers
    )
    bars_map = payload.get("bars") if isinstance(payload, dict) else None
    if not isinstance(bars_map, dict):
        raise RuntimeError("Alpaca 响应缺少 bars 字段")
    candidates = [symbol, symbol.upper(), symbol.lower()]
    bars: list[dict[str, Any]] = []
    for key in candidates:
        bars = bars_map.get(key) or []
        if bars:
            break
    if len(bars) < 2:
        raise RuntimeError("Alpaca 未返回足够的时间序列")
    ordered = sorted(bars, key=lambda item: str(item.get("t")))
    prev, latest = ordered[-2], ordered[-1]
    close = _safe_float(latest.get("c"))
    prev_close = _safe_float(prev.get("c"))
    if close is None or prev_close in (None, 0):
        raise RuntimeError("Alpaca 时间序列缺少收盘价")
    raw_ts = str(latest.get("t"))
    day = raw_ts.split("T")[0] if "T" in raw_ts else raw_ts[:10]
    change_pct = (close - prev_close) / prev_close * 100
    return _QuoteSnapshot(
        day=day, close=round(close, 4), change_pct=round(change_pct, 4), source="alpaca"
    )


def _fetch_quote_from_alpha(symbol: str, api_key: str) -> _QuoteSnapshot:
    series = _fetch_alpha_series(symbol, api_key)
    day, close, change_pct = _extract_close_change(series)
    return _QuoteSnapshot(
        day=day,
        close=round(close, 4),
        change_pct=round(change_pct, 4),
        source="alpha_vantage",
    )


def _fetch_yahoo_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    joined = ",".join(sorted(set(symbols)))
    urls = [
        "https://query2.finance.yahoo.com/v10/finance/quote",
        "https://query1.finance.yahoo.com/v10/finance/quote",
        "https://query2.finance.yahoo.com/v7/finance/quote",
        "https://query1.finance.yahoo.com/v7/finance/quote",
        "https://query2.finance.yahoo.com/v6/finance/quote",
    ]
    headers = {
        "Accept": "application/json",
        "User-Agent": BROWSER_USER_AGENT,
        "Referer": "https://finance.yahoo.com/",
        "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
        "Connection": "keep-alive",
    }
    last_error: Exception | None = None
    for url in urls:
        try:
            payload = _request_json(url, params={"symbols": joined}, headers=headers)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_yahoo_quotes" + " 捕获到异常", exc_info=True)
            last_error = exc
            continue

        items = (payload.get("quoteResponse") or {}).get("result") or []
        if not items:
            last_error = RuntimeError("empty response")
            continue

        results: dict[str, dict[str, Any]] = {}
        for item in items:
            symbol = item.get("symbol") if isinstance(item, dict) else None
            if not symbol:
                continue
            results[symbol] = {
                "changesPercentage": item.get("regularMarketChangePercent"),
                "pe": item.get("trailingPE"),
                "priceToSalesRatioTTM": item.get("priceToSalesTrailing12Months"),
                "marketCap": item.get("marketCap"),
                "price": item.get("regularMarketPrice"),
            }
        if results:
            return results
    raise RuntimeError(f"Yahoo Finance 未返回报价: {last_error or 'empty'}")


def _fetch_price_only_quotes(
    symbols: list[str], api_keys: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    alpaca_key: str | None = None
    alpaca_secret: str | None = None
    fmp_key: str | None = None
    if api_keys:
        alpaca_key = _coerce_api_key(api_keys.get("alpaca_key_id"))
        alpaca_secret = _coerce_api_key(api_keys.get("alpaca_secret"))
        fmp_key = _coerce_api_key(api_keys.get("financial_modeling_prep"))
    allow_yahoo = _yahoo_allowed()
    for symbol in symbols:
        snapshot: _QuoteSnapshot | None = None
        try:
            snapshot = _fetch_quote_from_stooq(symbol)
        except Exception:  # noqa: BLE001
            logger.warning("_fetch_price_only_quotes" + " 捕获到异常", exc_info=True)
            snapshot = None
        if not snapshot and alpaca_key and alpaca_secret:
            try:
                snapshot = _fetch_quote_from_alpaca(symbol, alpaca_key, alpaca_secret)
            except Exception:  # noqa: BLE001
                logger.warning("_fetch_price_only_quotes" + " 捕获到异常", exc_info=True)
                snapshot = None
        if not snapshot and fmp_key:
            try:
                snapshot = _fetch_quote_from_fmp(symbol, fmp_key)
            except Exception:  # noqa: BLE001
                logger.warning("_fetch_price_only_quotes" + " 捕获到异常", exc_info=True)
                snapshot = None
        if not snapshot and allow_yahoo:
            try:
                snapshot = _fetch_quote_from_yahoo(symbol)
            except Exception:  # noqa: BLE001
                logger.warning("_fetch_price_only_quotes" + " 捕获到异常", exc_info=True)
                snapshot = None
        if not snapshot:
            continue
        results[symbol] = {
            "changesPercentage": snapshot.change_pct,
            "pe": None,
            "priceToSalesRatioTTM": None,
            "marketCap": None,
            "price": snapshot.close,
            "source": snapshot.source,
        }
        _sleep(0.2)
    if not results:
        raise RuntimeError("price-only fallback 无法获取任何报价")
    return results
