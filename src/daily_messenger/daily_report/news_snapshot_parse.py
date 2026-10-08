"""Conservative parsing of unreviewed StreetAccount source snapshots."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

MAX_BYTES = 1_048_576
SOURCE_URL = "https://www.streetaccount.com/rss/rss.xml"
SECTION_KEYS = ("market", "drivers", "company_news", "macro", "gainers", "losers")


class _Bullets(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.hidden = 0
        self.parts: list[str] = []
        self.items: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "li":
            if not self.depth:
                self.parts = []
            self.depth += 1

    def handle_data(self, data: str) -> None:
        if self.depth and not self.hidden:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "li":
            self.depth -= 1
            if not self.depth:
                self.items.append(" ".join(" ".join(self.parts).split()))


def _xml(raw: bytes) -> ET.Element:
    if len(raw) > MAX_BYTES:
        raise ValueError("source exceeds 1 MiB")
    try:
        text = raw.decode("utf-8-sig")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper() or "\0" in text:
            raise ValueError("DTD, entities and non-UTF8 XML are not supported")
        return ET.fromstring(text)  # noqa: S314 -- DTD/entity declarations rejected above
    except (ET.ParseError, UnicodeDecodeError) as exc:
        raise ValueError("invalid UTF8 RSS XML") from exc


def _source_time(root: ET.Element) -> datetime:
    try:
        result = parsedate_to_datetime(root.findtext("./channel/lastBuildDate") or "")
    except (ValueError, TypeError) as exc:
        raise ValueError("missing or invalid channel build timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("channel build timestamp requires timezone")
    return result.astimezone(UTC)


def _blocks(item: ET.Element) -> list[str]:
    parser = _Bullets()
    parser.feed(item.findtext("description") or "")
    if parser.depth or parser.hidden or any(not text for text in parser.items):
        return []
    return parser.items


def _layout(items: list[ET.Element], blocks: list[list[str]]) -> bool:
    if len(items) != 3 or len(blocks[0]) != 4 or not all(blocks):
        return False
    titles = [item.findtext("title", "").strip().lower() for item in items]
    if not (
        titles[0].startswith("us equities")
        and titles[1] == "notable gainers:"
        and titles[2] == "notable decliners:"
    ):
        return False
    summary = blocks[0]
    anchors = (
        r"^US equities",
        r"Session|market|trade",
        r"^[A-Z]{1,6}\b",
        r"Fed|FOMC|inflation|auction",
    )
    return all(re.search(pattern, text) for pattern, text in zip(anchors, summary, strict=True))


def _issues(
    build: datetime, expected: date, captured: datetime, blocks: list[list[str]]
) -> list[str]:
    issues = []
    local_build = build.astimezone(ZoneInfo("America/New_York"))
    if local_build.date() != expected:
        issues.append("session_mismatch")
    if build > captured:
        issues.append("build_after_capture")
    calendar = xcals.get_calendar(
        "XNYS", start=f"{expected.year}-01-01", end=f"{expected.year}-12-31"
    )
    if not calendar.is_session(expected.isoformat()):
        issues.append("non_trading_day")
    elif build < calendar.session_close(expected.isoformat()).to_pydatetime():
        issues.append("preclose_build")
    text = blocks[0][0] if blocks and blocks[0] else ""
    weekdays = re.findall(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday) trading\b", text)
    if weekdays != [expected.strftime("%A")]:
        issues.append("weekday_mismatch")
    return issues


def _sections(items: list[ET.Element], blocks: list[list[str]]) -> list[dict[str, Any]]:
    result = []
    mapping = ((0, 0), (0, 1), (0, 2), (0, 3), (1, None), (2, None))
    for key, (item_index, bullet_index) in zip(SECTION_KEYS, mapping, strict=True):
        selected = (
            blocks[item_index] if bullet_index is None else [blocks[item_index][bullet_index]]
        )
        entries = []
        for index, text in enumerate(selected):
            position = index if bullet_index is None else bullet_index
            entries.append(
                {
                    "id": f"{key}-{index + 1}",
                    "text": text,
                    "locator": f"rss/channel/item[{item_index + 1}]/description/li[{position + 1}]",
                    "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "published_at": None,
                }
            )
        if key == "market":
            title = items[0].findtext("title", "")
            entries.insert(
                0,
                {
                    "id": "market-title",
                    "text": title,
                    "locator": "rss/channel/item[1]/title",
                    "content_sha256": hashlib.sha256(title.encode()).hexdigest(),
                    "published_at": None,
                },
            )
        result.append({"key": key, "blocks": entries})
    return result


def parse_snapshot(raw: bytes, expected: date, captured: datetime, mode: str) -> dict[str, Any]:
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("capture timestamp requires timezone")
    if mode not in {"live", "replay"}:
        raise ValueError("invalid capture mode")
    root = _xml(raw)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("not an RSS channel")
    build = _source_time(root)
    items = root.findall("./channel/item")
    blocks = [_blocks(item) for item in items]
    issues = _issues(build, expected, captured, blocks)
    if not _layout(items, blocks):
        issues.append("layout_changed")
    return {
        "schema_version": "market.news-snapshot.v1",
        "source_url": SOURCE_URL,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "capture_mode": mode,
        "market_date": expected.isoformat(),
        "captured_at": captured.astimezone(UTC).isoformat(),
        "channel_last_build": build.isoformat(),
        "item_timestamps": [item.findtext("{*}updated") for item in items],
        "publication_time_status": "unresolved",
        "review_status": "needs_review",
        "status": "quarantined" if issues else "needs_review",
        "issues": issues,
        "sections": [] if issues else _sections(items, blocks),
    }
