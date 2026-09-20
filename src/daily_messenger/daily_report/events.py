"""Normalize point-in-time market events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from .models import MarketEvent


def _event_id(row: Mapping[str, Any]) -> str:
    value = str(row.get("id") or "").strip()
    if value:
        return value
    title = str(row.get("title") or "event").strip().lower().replace(" ", "-")
    source_time = row.get("source_time")
    return f"{title}:{source_time}"


def _source_time(value: Any, as_of: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return as_of


def build_market_events(
    raw_events: Iterable[Mapping[str, Any]], *, as_of: datetime
) -> list[MarketEvent]:
    result: dict[str, MarketEvent] = {}
    for row in raw_events:
        event = MarketEvent(
            id=_event_id(row),
            event_type=str(row.get("event_type") or "news"),
            title=str(row.get("title") or "Untitled event"),
            actual=row.get("actual"),
            previous=row.get("previous"),
            forecast=row.get("forecast"),
            revised=row.get("revised"),
            source=str(row.get("source") or "unknown"),
            source_url=str(row.get("source_url") or "") or None,
            source_time=_source_time(row.get("source_time"), as_of),
            quality=str(row.get("quality") or "ok"),
        )
        existing = result.get(event.id)
        if existing is None or existing.quality != "ok" and event.quality == "ok":
            result[event.id] = event
    return sorted(result.values(), key=lambda item: (item.source_time, item.id))


def filter_events_as_of(events: Iterable[MarketEvent], as_of: datetime) -> list[MarketEvent]:
    return [event for event in events if event.source_time <= as_of]
