"""RSS and arXiv event fetching for the AI market-news fetcher.

Pure physical split-out of ``ai_news.py``. Holds the XML parsing helpers and the
two auxiliary feed fetchers (``_fetch_ai_rss_events`` / ``_fetch_arxiv_events``)
that are not part of the LLM provider flow.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree as ET

import requests

from daily_messenger.etl.http import (
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from daily_messenger.etl.types import FetchStatus

from .ai_news_common import _sleep

logger = logging.getLogger(__name__)


def _rss_text(node: ET.Element, *paths: str) -> str:
    for path in paths:
        text = node.findtext(path)
        if text:
            return text.strip()
    return ""


def _normalize_rss_date(raw: str) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except Exception:  # noqa: BLE001
        logger.warning("_normalize_rss_date" + " 捕获到异常", exc_info=True)
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.date().isoformat()


def _fetch_ai_rss_events(
    feeds: list[str],
) -> tuple[list[dict[str, Any]], list[FetchStatus]]:
    events: list[dict[str, Any]] = []
    statuses: list[FetchStatus] = []
    for idx, url in enumerate(feeds, start=1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_ai_rss_events" + " 捕获到异常", exc_info=True)
            statuses.append(
                FetchStatus(
                    name=f"ai_rss_{idx}",
                    ok=False,
                    message=f"RSS 请求失败: {url} ({exc})",
                )
            )
            continue
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            statuses.append(
                FetchStatus(
                    name=f"ai_rss_{idx}",
                    ok=False,
                    message=f"RSS 解析失败: {url} ({exc})",
                )
            )
            continue

        items = root.findall(".//item") or root.findall(".//{*}entry")
        feed_events: list[dict[str, Any]] = []
        for item in items[:5]:
            title = _rss_text(item, "title", "{*}title") or "更新"
            date_text = _rss_text(
                item,
                "pubDate",
                "{*}updated",
                "{*}published",
                "{*}lastBuildDate",
            )
            normalized_date = _normalize_rss_date(date_text)
            if not normalized_date:
                normalized_date = datetime.now(UTC).strftime("%Y-%m-%d")
            link_url = _rss_text(item, "link", "{*}link")
            if not link_url:
                link_node = item.find("link") or item.find("{*}link")
                if link_node is not None:
                    href = link_node.get("href")
                    if href:
                        link_url = href.strip()
                    elif link_node.text:
                        link_url = link_node.text.strip()
            feed_events.append(
                {
                    "title": title,
                    "date": normalized_date,
                    "impact": "medium",
                    "source": url,
                    "url": link_url or "",
                }
            )
        events.extend(feed_events)
        statuses.append(
            FetchStatus(
                name=f"ai_rss_{idx}",
                ok=True,
                message=f"RSS 获取成功: {url}（{len(feed_events)} 条）",
            )
        )
    return events, statuses


def _fetch_arxiv_events(
    params: dict[str, Any], throttle: float
) -> tuple[list[dict[str, Any]], FetchStatus]:
    url = "https://export.arxiv.org/api/query"
    try:
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_arxiv_events" + " 捕获到异常", exc_info=True)
        return [], FetchStatus(name="arxiv", ok=False, message=f"arXiv 请求失败: {exc}")

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        return [], FetchStatus(name="arxiv", ok=False, message=f"arXiv 响应解析失败: {exc}")

    events: list[dict[str, Any]] = []
    for entry in root.findall(".//{*}entry"):
        title = (_rss_text(entry, "{*}title") or "").replace("\n", " ").strip()
        if not title:
            title = "arXiv 更新"
        date_text = _rss_text(entry, "{*}updated", "{*}published")
        normalized_date = None
        if date_text:
            try:
                normalized_date = (
                    datetime.fromisoformat(date_text.replace("Z", "+00:00")).date().isoformat()
                )
            except ValueError:
                normalized_date = _normalize_rss_date(date_text)
        if not normalized_date:
            normalized_date = datetime.now(UTC).strftime("%Y-%m-%d")
        entry_url = _rss_text(entry, "{*}id")
        events.append(
            {
                "title": f"arXiv: {title}",
                "date": normalized_date,
                "impact": "low",
                "source": "arxiv",
                "url": entry_url,
            }
        )

    if throttle > 0:
        _sleep(throttle)

    return events, FetchStatus(name="arxiv", ok=True, message=f"arXiv 返回 {len(events)} 篇文章")
