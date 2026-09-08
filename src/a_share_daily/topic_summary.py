"""Consumer validation for the DailyWatch20 topic summary artifact."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "daily_watch20.topic_summary.v1"
ARTIFACT_TYPE = "daily_watch20_topic_summary"


class TopicSummaryError(ValueError):
    """Raised when a topic summary cannot be safely consumed."""


def _date_key(value: object, *, field: str) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise TopicSummaryError(f"{field} must be YYYYMMDD")
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise TopicSummaryError(f"{field} must be a valid YYYYMMDD date") from exc
    return text


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TopicSummaryError(f"topic summary is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TopicSummaryError(f"cannot read topic summary: {path}") from exc
    if not isinstance(payload, dict):
        raise TopicSummaryError("topic summary must be a JSON object")
    return payload


def _validate_dates(
    payload: Mapping[str, Any],
    *,
    expected_source_date: str | None,
    expected_signal_date: str | None,
) -> tuple[str, str]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise TopicSummaryError(
            f"unsupported topic summary schema: {payload.get('schema_version')!r}"
        )
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise TopicSummaryError("topic summary artifact_type is invalid")
    source = _date_key(payload.get("source_date"), field="source_date")
    signal = _date_key(payload.get("signal_date"), field="signal_date")
    if signal < source:
        raise TopicSummaryError("signal_date must follow source_date")
    if signal == source and payload.get("source") not in {
        "dc_concept",
        "hotspot_composite_v1",
    }:
        raise TopicSummaryError(
            "same-day topic summaries must use dc_concept or hotspot_composite_v1"
        )
    if expected_source_date is not None and source != _date_key(
        expected_source_date, field="expected_source_date"
    ):
        raise TopicSummaryError(
            f"topic summary source_date={source} does not match expected {expected_source_date}"
        )
    if expected_signal_date is not None and signal != _date_key(
        expected_signal_date, field="expected_signal_date"
    ):
        raise TopicSummaryError(
            f"topic summary signal_date={signal} does not match expected {expected_signal_date}"
        )
    return source, signal


def _validate_topics(raw_topics: object) -> list[dict[str, Any]]:
    if not isinstance(raw_topics, list) or not raw_topics:
        raise TopicSummaryError("topic summary topics must be non-empty")
    topics: list[dict[str, Any]] = []
    previous_rank = 0
    total_weight = 0.0
    for index, raw in enumerate(raw_topics):
        if not isinstance(raw, Mapping):
            raise TopicSummaryError(f"topic summary topics[{index}] must be an object")
        topic = str(raw.get("topic") or "").strip()
        if not topic:
            raise TopicSummaryError(f"topic summary topics[{index}].topic is empty")
        try:
            count = int(str(raw.get("count")))
            rank = int(str(raw.get("rank")))
            weight = float(str(raw.get("weight")))
        except (TypeError, ValueError) as exc:
            raise TopicSummaryError(
                f"topic summary topics[{index}] has invalid numeric fields"
            ) from exc
        if count <= 0 or rank != index + 1 or rank <= previous_rank:
            raise TopicSummaryError(f"topic summary topics[{index}] rank/count is invalid")
        if not math.isfinite(weight) or weight < 0:
            raise TopicSummaryError(f"topic summary topics[{index}] weight is invalid")
        previous_rank = rank
        total_weight += weight
        topics.append({"topic": topic, "count": count, "weight": weight, "rank": rank})
    if total_weight <= 0:
        raise TopicSummaryError("topic summary total weight must be positive")
    return topics


def _validate_quality(payload: Mapping[str, Any], topics: list[dict[str, Any]]) -> None:
    quality = payload.get("quality")
    if not isinstance(quality, Mapping) or quality.get("status") != "passed":
        raise TopicSummaryError("topic summary quality status is not passed")
    if quality.get("selected_count") != sum(item["count"] for item in topics):
        raise TopicSummaryError("topic summary selected_count is inconsistent")
    if quality.get("topic_count") != len(topics):
        raise TopicSummaryError("topic summary topic_count is inconsistent")


def load_topic_summary(
    path: Path,
    *,
    expected_source_date: str | None = None,
    expected_signal_date: str | None = None,
) -> dict[str, Any]:
    """Load and validate one owner-published topic summary."""

    payload = _read_payload(path)
    source, signal = _validate_dates(
        payload,
        expected_source_date=expected_source_date,
        expected_signal_date=expected_signal_date,
    )
    topics = _validate_topics(payload.get("topics"))
    _validate_quality(payload, topics)
    return {
        **payload,
        "source_date": source,
        "signal_date": signal,
        "topics": topics,
    }


__all__ = ["ARTIFACT_TYPE", "SCHEMA_VERSION", "TopicSummaryError", "load_topic_summary"]
