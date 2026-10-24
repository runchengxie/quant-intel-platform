"""Strict, language-neutral public weekly report contract."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime

SCHEMA = "market_intel_pages.weekly_recap.v1"
INDEX_SCHEMA = "market_intel_pages.weekly_recaps.v1"
HASH = re.compile(r"[0-9a-f]{64}")


def content_hash(payload: dict) -> str:
    """Hash canonical UTF-8 JSON, excluding only the digest itself."""
    return hashlib.sha256(
        json.dumps(
            {k: v for k, v in payload.items() if k != "content_hash"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def exact(value: object, keys: str) -> dict:
    """Reject unknown fields at every public object boundary."""
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError("weekly object has missing or unexpected fields")
    return value


def iso_date(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("weekly date must be ISO date")
    date.fromisoformat(value)
    return value


def number(value: object, minimum: float = -math.inf, maximum: float = math.inf) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError("invalid weekly numeric value")


def _series(rows: object, kind: str, day: str) -> None:
    keys = (
        "date return_12w_percent wealth_index"
        if kind == "value"
        else "date relative_strength small_crowding large_crowding"
    )
    if not isinstance(rows, list) or not 1 <= len(rows) <= (104 if kind == "value" else 252):
        raise ValueError("invalid weekly series length")
    dates = []
    for raw in rows:
        row = exact(raw, keys)
        dates.append(iso_date(row["date"]))
        for key, value in row.items():
            if key == "date":
                continue
            if key.endswith("crowding"):
                number(value, 0, 1)
            elif key in {"wealth_index", "relative_strength"}:
                number(value, 0)
                if value <= 0:
                    raise ValueError("weekly index must be positive")
            else:
                number(value)
    if dates != sorted(set(dates)) or dates[-1] != day:
        raise ValueError("weekly series dates are stale or unordered")


def validate_weekly_recap(payload: object) -> dict:
    """Validate an allowlisted public payload and its canonical digest."""
    p = exact(
        payload,
        "schema_version publication report_id date generated_at content_hash markdown "
        "source_url image summary series sources",
    )
    day = iso_date(p["date"])
    if (
        p["schema_version"] != SCHEMA
        or p["publication"] != "public"
        or p["report_id"] != f"{day}-weekly"
    ):
        raise ValueError("invalid weekly identity or publication")
    if date.fromisoformat(day).weekday() != 4:
        raise ValueError("weekly cutoff must be Friday")
    if not isinstance(p["generated_at"], str):
        raise ValueError("invalid weekly generation timestamp")
    timestamp = datetime.fromisoformat(p["generated_at"])
    if timestamp.tzinfo is None or timestamp.date() < date.fromisoformat(day):
        raise ValueError("invalid weekly generation timestamp")
    if (
        not isinstance(p["markdown"], str)
        or not 1 <= len(p["markdown"].encode()) <= 1_000_000
        or "\x00" in p["markdown"]
    ):
        raise ValueError("invalid weekly Markdown")
    if p["source_url"] != f"reports/{day}-weekly.md":
        raise ValueError("unsafe weekly Markdown URL")
    _image(p["image"], day)
    _summary(p["summary"])
    series = exact(p["series"], "value size")
    for kind in series:
        _series(series[kind], kind, day)
    sources = exact(p["sources"], "value size")
    for source in sources.values():
        source = exact(source, "schema_version as_of sha256")
        if (
            source["schema_version"] != "research.weekly_analysis.v1"
            or source["as_of"] != day
            or not isinstance(source["sha256"], str)
            or not HASH.fullmatch(source["sha256"])
        ):
            raise ValueError("invalid weekly source provenance")
    if p["content_hash"] != content_hash(p):
        raise ValueError("weekly content hash mismatch")
    return p


def _image(raw: object, day: str) -> None:
    image = exact(raw, "source_url sha256 width height")
    if (
        image["source_url"] != f"reports/{day}-weekly.png"
        or not isinstance(image["sha256"], str)
        or not HASH.fullmatch(image["sha256"])
    ):
        raise ValueError("invalid weekly image identity")
    for key in ("width", "height"):
        if type(image[key]) is not int or not 1 <= image[key] <= 20000:
            raise ValueError("invalid weekly image dimensions")


def _summary(raw: object) -> None:
    summary = exact(
        raw,
        "value_regime value_streak_weeks value_return_12w_percent small_crowding large_crowding size_signal",
    )
    if summary["value_regime"] not in ("MOMENTUM", "NEUTRAL") or summary["size_signal"] not in (
        "large_cap",
        "small_cap",
        "insufficient",
    ):
        raise ValueError("invalid owner enum")
    if type(summary["value_streak_weeks"]) is not int or summary["value_streak_weeks"] < 1:
        raise ValueError("invalid weekly streak")
    number(summary["value_return_12w_percent"])
    for key in ("small_crowding", "large_crowding"):
        number(summary[key], 0, 1)
