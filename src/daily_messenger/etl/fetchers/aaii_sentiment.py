"""Fetch AAII weekly investor sentiment survey results."""

from __future__ import annotations

import datetime as dt
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import requests

from .cboe_putcall import fetch as _cboe_putcall_fetch

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20
RSS_URL = "https://insights.aaii.com/feed"


@dataclass
class FetchStatus:
    name: str
    ok: bool
    message: str = ""


def _init_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _resolve_latest_story(session: requests.Session) -> str | None:
    try:
        response = session.get(RSS_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception:  # noqa: BLE001
        logger.warning("_resolve_latest_story" + " 捕获到异常", exc_info=True)
        return None
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return None
    channel = root.find("channel")
    if channel is None:
        return None
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        if "Sentiment Survey" in title:
            return link
    return None


def _parse_article(html: str) -> dict[str, float] | None:
    pattern = re.compile(
        r"(?is)Bullish[^0-9]*([0-9]+(?:\.[0-9]+)?)%.*?Neutral[^0-9]*([0-9]+(?:\.[0-9]+)?)%.*?Bearish[^0-9]*([0-9]+(?:\.[0-9]+)?)%"
    )
    match = pattern.search(html)
    if not match:
        return None
    try:
        bull, neutral, bear = (float(match.group(i)) for i in range(1, 4))
    except ValueError:
        return None
    return {
        "bullish_pct": round(bull, 2),
        "neutral_pct": round(neutral, 2),
        "bearish_pct": round(bear, 2),
        "bull_bear_spread": round(bull - bear, 2),
    }


def _parse_week(html: str) -> str | None:
    date_pattern = re.compile(
        r"(?i)(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"
    )
    match = date_pattern.search(html)
    if not match:
        return None
    try:
        parsed = dt.datetime.strptime(match.group(0), "%B %d, %Y")
    except ValueError:
        return None
    return parsed.date().isoformat()


def fetch() -> tuple[dict[str, dict[str, object]], FetchStatus]:
    session = _init_session()
    link = _resolve_latest_story(session)
    if not link:
        return {}, FetchStatus(name="aaii_sentiment", ok=False, message="未能定位最新情绪文章")

    try:
        response = session.get(link, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch" + " 捕获到异常", exc_info=True)
        return {}, FetchStatus(name="aaii_sentiment", ok=False, message=f"AAII 请求失败: {exc}")

    metrics = _parse_article(response.text)
    if metrics is None:
        return {}, FetchStatus(name="aaii_sentiment", ok=False, message="AAII 页面缺少情绪百分比")

    week = _parse_week(response.text) or dt.date.today().isoformat()

    payload: dict[str, dict[str, object]] = {
        "aaii": {
            "week": week,
            **metrics,
            "source": "aaii_insights_substack",
            "link": link,
        }
    }

    return payload, FetchStatus(name="aaii_sentiment", ok=True, message="AAII 情绪数据已更新")


def _merge_sentiment_source(
    sentiment_data: dict[str, Any],
    payload: dict[str, Any] | None,
    status: Any,
    previous_sentiment: dict[str, Any],
    fallback_key: str,
    fallback_status_name: str,
    fallback_message: str,
    statuses: list[Any],
) -> bool:
    statuses.append(status)
    if getattr(status, "ok", False) and payload:
        sentiment_data.update(payload)
        return True

    previous_payload = previous_sentiment.get(fallback_key)
    if isinstance(previous_payload, dict):
        sentiment_data[fallback_key] = previous_payload
        statuses.append(FetchStatus(name=fallback_status_name, ok=True, message=fallback_message))
    return False


def _fetch_sentiment_payload(
    previous_sentiment: dict[str, Any],
    statuses: list[Any],
) -> tuple[dict[str, Any], bool]:
    sentiment_data: dict[str, Any] = {}
    put_call_payload, put_call_status = _cboe_putcall_fetch()
    put_call_ok = _merge_sentiment_source(
        sentiment_data,
        put_call_payload,
        put_call_status,
        previous_sentiment,
        "put_call",
        "cboe_put_call_fallback",
        "使用上一期 Put/Call 数据",
        statuses,
    )
    aaii_payload, aaii_status = fetch()
    aaii_ok = _merge_sentiment_source(
        sentiment_data,
        aaii_payload,
        aaii_status,
        previous_sentiment,
        "aaii",
        "aaii_sentiment_fallback",
        "使用上一期 AAII 数据",
        statuses,
    )
    return sentiment_data, put_call_ok and aaii_ok
