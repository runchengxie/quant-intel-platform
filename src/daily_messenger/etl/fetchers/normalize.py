"""事件规范化与来源链解析工具。

从 `daily_messenger.etl.run_fetch` 拆出的纯逻辑：清理事件文本、校验来源
URL、规范化 sourceChain、把原始事件条目归一化为报告用的结构化字典。无网络
依赖，便于独立测试。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from html.parser import HTMLParser
from typing import Any

EVENT_METADATA_FIELDS = {
    "title",
    "date",
    "impact",
    "country",
    "source",
    "url",
    "published_at",
    "market",
    "label",
    "category",
}


def _clean_event_text(value: Any, max_len: int = 300) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())[:max_len].rstrip()


def _valid_event_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("https://") or lowered.startswith("http://")


def _append_source_chain_entry(
    chain: list[dict[str, str]],
    *,
    source: Any = "",
    url: Any = "",
    title: Any = "",
) -> None:
    source_text = _clean_event_text(source, 120)
    url_text = _clean_event_text(url, 400)
    title_text = _clean_event_text(title, 160)
    if url_text and not _valid_event_url(url_text):
        url_text = ""
    if not (source_text or url_text):
        return
    entry = {"source": source_text, "url": url_text}
    if title_text:
        entry["title"] = title_text
    marker = (entry.get("source", ""), entry.get("url", ""), entry.get("title", ""))
    existing = {
        (item.get("source", ""), item.get("url", ""), item.get("title", "")) for item in chain
    }
    if marker not in existing:
        chain.append(entry)


def _normalize_source_chain(
    entry: Mapping[str, Any],
    *,
    fallback_source: str = "",
    fallback_url: str = "",
) -> list[dict[str, str]]:
    chain: list[dict[str, str]] = []
    raw_chain = entry.get("sourceChain") or entry.get("source_chain") or entry.get("sources")
    if isinstance(raw_chain, list):
        for raw_item in raw_chain:
            if isinstance(raw_item, Mapping):
                _append_source_chain_entry(
                    chain,
                    source=raw_item.get("source") or raw_item.get("name"),
                    url=raw_item.get("url"),
                    title=raw_item.get("title"),
                )
            elif isinstance(raw_item, str):
                _append_source_chain_entry(chain, source=raw_item)

    raw_items = entry.get("items")
    if isinstance(raw_items, list):
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping):
                continue
            _append_source_chain_entry(
                chain,
                source=raw_item.get("source"),
                url=raw_item.get("url"),
                title=raw_item.get("title"),
            )

    _append_source_chain_entry(
        chain,
        source=entry.get("source") or fallback_source,
        url=entry.get("url") or fallback_url,
        title=entry.get("title"),
    )
    return chain


def _normalize_raw_event(
    entry: Mapping[str, Any],
    *,
    fallback_source: str = "",
    fallback_url: str = "",
) -> dict[str, Any] | None:
    title = _clean_event_text(entry.get("title"), 180)
    if not title:
        return None
    normalized: dict[str, Any] = {"title": title}
    for field in EVENT_METADATA_FIELDS - {"title"}:
        value = _clean_event_text(entry.get(field), 400 if field == "url" else 160)
        if not value:
            continue
        if field == "url" and not _valid_event_url(value):
            continue
        normalized[field] = value

    chain = _normalize_source_chain(
        entry,
        fallback_source=fallback_source,
        fallback_url=fallback_url,
    )
    if chain:
        normalized["sourceChain"] = chain
        if not normalized.get("source"):
            normalized["source"] = chain[0].get("source", "")
        if not normalized.get("url"):
            first_url = next((item.get("url", "") for item in chain if item.get("url")), "")
            if first_url:
                normalized["url"] = first_url
    return normalized


def _normalize_raw_events_payload(
    events: Iterable[Mapping[str, Any]],
    ai_updates: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_events = [
        item for item in (_normalize_raw_event(entry) for entry in events) if item is not None
    ]
    normalized_ai_updates = [
        item
        for item in (
            _normalize_raw_event(entry, fallback_source=str(entry.get("provider") or ""))
            for entry in ai_updates
        )
        if item is not None
    ]
    return normalized_events, normalized_ai_updates


class _HTMLTableParser(HTMLParser):
    """Extract rows from a simple HTML table."""

    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._buffer: list[str] = []
        self._current: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # type: ignore[override]
        if tag == "tr":
            self._current = []
        elif tag in {"td", "th"}:
            self._capture = True
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"td", "th"} and self._capture:
            value = "".join(self._buffer).strip()
            self._current.append(value)
            self._capture = False
        elif tag == "tr" and self._current:
            self.rows.append(self._current)

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._capture:
            self._buffer.append(data)
