"""事件抓取（events 组）。

从 daily_messenger.etl.run_fetch 拆出的事件源抓取函数：Trading Economics
日历与 Finnhub 财报日历。事件聚合与排序（_fetch_calendar_events /
_fetch_news_events / _fetch_events_payload）仍留在 run_fetch，作为编排胶水调用
本模块。共享工具取自 etl.fetchers._common 与 etl.http。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from daily_messenger.etl.config import coerce_api_key as _coerce_api_key
from daily_messenger.etl.fetchers._common import _safe_float
from daily_messenger.etl.http import request_json as _request_json
from daily_messenger.etl.types import FetchStatus

logger = logging.getLogger(__name__)

TE_GUEST_CREDENTIAL = "guest:guest"

MAX_EVENT_ITEMS = 12


def _fetch_events_real(
    trading_day: str, api_keys: dict[str, Any]
) -> tuple[list[dict[str, Any]], FetchStatus]:
    credential = _coerce_api_key(api_keys.get("trading_economics"))
    if not credential or credential.strip().lower() == TE_GUEST_CREDENTIAL:
        return [], FetchStatus(
            name="events",
            ok=False,
            message="Trading Economics 未配置有效 API 凭证；guest:guest 已停用",
        )
    params = {"c": credential, "format": "json"}
    try:
        payload = _request_json("https://api.tradingeconomics.com/calendar", params=params)
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_events_real" + " 捕获到异常", exc_info=True)
        detail = str(exc)
        if "401" in detail:
            detail = f"凭证无效或套餐未开通 Calendar API: {detail}"
        elif "410" in detail or "guest account has been discontinued" in detail:
            detail = f"guest 账号已停用: {detail}"
        return [], FetchStatus(
            name="events", ok=False, message=f"Trading Economics 请求失败: {detail}"
        )

    base_date = datetime.strptime(trading_day, "%Y-%m-%d").date()
    window_end = base_date + timedelta(days=5)
    events: list[dict[str, Any]] = []
    for entry in payload:
        date_str = entry.get("Date")
        event_name = entry.get("Event")
        if not date_str or not event_name:
            continue
        try:
            event_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if not (base_date <= event_date <= window_end):
            continue

        importance = str(entry.get("Importance", "medium")).lower()
        if importance not in {"low", "medium", "high"}:
            importance = "medium"
        events.append(
            {
                "title": event_name,
                "date": event_date.strftime("%Y-%m-%d"),
                "impact": importance,
                "country": entry.get("Country"),
                "source": "Trading Economics",
                "url": "https://tradingeconomics.com/calendar",
            }
        )
        if len(events) >= 8:
            break

    if not events:
        return [], FetchStatus(name="events", ok=False, message="Trading Economics 未返回可用事件")

    return events, FetchStatus(name="events", ok=True, message="Trading Economics 事件日历已获取")


def _finnhub_record_to_event(item: dict[str, Any], event_date: Any) -> dict[str, Any] | None:
    symbol = item.get("symbol")
    eps_est = _safe_float(item.get("epsEstimate"))
    eps_actual = _safe_float(item.get("epsActual"))
    surprise_text = ""
    if eps_actual is not None and eps_est is not None:
        surprise = eps_actual - eps_est
        surprise_text = f" EPS {eps_actual:.2f}/{eps_est:.2f} ({surprise:+.2f})"
    session = str(item.get("time", "")).upper()
    if session in {"AMC", "POSTMARKET"}:
        session_label = "盘后"
    elif session in {"BMO", "PREMARKET"}:
        session_label = "盘前"
    else:
        session_label = ""
    title = f"{symbol} 财报"
    if session_label:
        title += f"（{session_label}）"
    if surprise_text:
        title += surprise_text
    market_cap = _safe_float(item.get("marketCapitalization"))
    impact = "high" if market_cap and market_cap >= 200_000 else "medium"
    return {
        "title": title,
        "date": event_date.strftime("%Y-%m-%d"),
        "impact": impact,
        "country": "US",
        "source": "Finnhub",
        "url": "https://finnhub.io/",
    }


def _fetch_finnhub_earnings(
    trading_day: str, api_keys: dict[str, Any]
) -> tuple[list[dict[str, Any]], FetchStatus]:
    api_key = api_keys.get("finnhub")
    if not api_key:
        return [], FetchStatus(name="finnhub_earnings", ok=False, message="缺少 Finnhub API Key")

    start = datetime.strptime(trading_day, "%Y-%m-%d").date()
    end = start + timedelta(days=5)
    params = {
        "from": trading_day,
        "to": end.strftime("%Y-%m-%d"),
        "token": api_key,
    }
    try:
        payload = _request_json("https://finnhub.io/api/v1/calendar/earnings", params=params)
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_finnhub_earnings" + " 捕获到异常", exc_info=True)
        return [], FetchStatus(
            name="finnhub_earnings", ok=False, message=f"Finnhub 请求失败: {exc}"
        )

    items = payload.get("earningsCalendar") or []
    events: list[dict[str, Any]] = []
    for item in items:
        date_str = item.get("date")
        symbol = item.get("symbol")
        if not date_str or not symbol:
            continue
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (start <= event_date <= end):
            continue
        event = _finnhub_record_to_event(item, event_date)
        if event is not None:
            events.append(event)

    if not events:
        return [], FetchStatus(name="finnhub_earnings", ok=False, message="Finnhub 未返回财报事件")

    events.sort(key=lambda item: item["date"])
    return events, FetchStatus(name="finnhub_earnings", ok=True, message="Finnhub 财报日历已获取")
