"""Public six-chart contract; this does not approve provider candidates."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from datetime import date, datetime
from urllib.parse import urlsplit

CHART_KEYS = ("dashboard", "moneyflow", "topic", "sentiment", "us_overnight", "weekly_chart")
SCHEMA = "market_intel.a_share_charts.v1"
TOP_FIELDS = {
    "schema_version",
    "publication",
    "report_id",
    "date",
    "kind",
    "generated_at",
    "charts",
    "content_sha256",
}
CARD_FIELDS = {"key", "title", "status", "reason", "points"}
POINT_FIELDS = {"label", "value", "unit", "observation_date", "source_label", "source_url"}
_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|bearer)\s*[:=]|\b(?:sk-|ghp_)[A-Za-z0-9_-]{8,}"
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    if value.startswith(("/", "\\", "file://")) or "/home/" in value or re.match(r"^[A-Za-z]:\\", value):
        raise ValueError(f"{field} contains a private path")
    if _SECRET.search(value):
        raise ValueError(f"{field} contains credentials")
    return value


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be ISO date")
    return parsed


def _source_url(value: object) -> str:
    source = _text(value, "source_url")
    parsed = urlsplit(source)
    host = parsed.hostname or ""
    private = host == "localhost" or host.endswith((".local", ".internal"))
    try:
        private = private or not ipaddress.ip_address(host).is_global
    except ValueError:
        private = private or "." not in host
    if parsed.scheme != "https" or not host or parsed.username or parsed.password or private:
        raise ValueError("source_url must be a public HTTPS URL")
    return source


def _validate_point(point: object, report_date: date) -> dict:
    if not isinstance(point, dict) or set(point) != POINT_FIELDS:
        raise ValueError("chart point field mismatch")
    value = point["value"]
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError("point value must be finite")
    observed = _date(point["observation_date"], "observation_date")
    if observed > report_date:
        raise ValueError("observation_date cannot follow report date")
    return {
        "label": _text(point["label"], "label"),
        "value": value,
        "unit": _text(point["unit"], "unit"),
        "observation_date": observed.isoformat(),
        "source_label": _text(point["source_label"], "source_label"),
        "source_url": _source_url(point["source_url"]),
    }


def _validate_card(card: object, key: str, report_date: date) -> dict:
    if not isinstance(card, dict) or set(card) != CARD_FIELDS or card.get("key") != key:
        raise ValueError(f"chart card field or key mismatch: {key}")
    status = card["status"]
    if status not in {"ok", "degraded", "missing", "skipped"} or not isinstance(card["points"], list):
        raise ValueError(f"chart status or points invalid: {key}")
    points = [_validate_point(point, report_date) for point in card["points"]]
    reason = card["reason"]
    if status in {"missing", "skipped"} and (points or not isinstance(reason, str) or not reason):
        raise ValueError(f"{status} chart must have only a reason: {key}")
    if status in {"ok", "degraded"} and not points:
        raise ValueError(f"{status} chart needs points: {key}")
    if status == "degraded" and (not isinstance(reason, str) or not reason):
        raise ValueError(f"degraded chart needs a reason: {key}")
    if reason is not None:
        reason = _text(reason, "reason")
    return {
        "key": key,
        "title": _text(card["title"], "title"),
        "status": status,
        "reason": reason,
        "points": points,
    }


def validate_public_chart(payload: object, *, expected_id: str | None = None) -> dict:
    """Rebuild a public snapshot from exact fields and verify its content hash."""
    if not isinstance(payload, dict) or set(payload) != TOP_FIELDS:
        raise ValueError("public chart field mismatch")
    if payload["schema_version"] != SCHEMA or payload["publication"] != "public":
        raise ValueError("only reviewed public chart schema is accepted")
    report_date = _date(payload["date"], "date")
    kind = payload["kind"]
    report_id = f"{report_date.isoformat()}-{kind}"
    if kind not in {"morning", "evening"} or payload["report_id"] != report_id:
        raise ValueError("report_id does not match date and kind")
    if expected_id is not None and expected_id != report_id:
        raise ValueError("chart identity differs from report identity")
    generated_at = payload["generated_at"]
    try:
        generated = datetime.fromisoformat(generated_at)
    except (TypeError, ValueError) as exc:
        raise ValueError("generated_at needs timezone") from exc
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("generated_at needs timezone")
    cards = payload["charts"]
    if not isinstance(cards, list) or len(cards) != len(CHART_KEYS):
        raise ValueError("exactly six chart cards are required")
    checked = [_validate_card(card, key, report_date) for card, key in zip(cards, CHART_KEYS, strict=True)]
    canonical = json.dumps(
        {key: value for key, value in payload.items() if key != "content_sha256"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    if hashlib.sha256(canonical).hexdigest() != payload["content_sha256"]:
        raise ValueError("chart content hash mismatch")
    return {**payload, "charts": checked}
