"""Validated, deliberately small candidates for public A-share report charts."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
from collections.abc import Mapping
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, cast
from urllib.parse import urlsplit

CHART_KEYS = ("dashboard", "moneyflow", "topic", "sentiment", "us_overnight", "weekly_chart")
SCHEMA = "market_intel.a_share_charts.v1"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|bearer)\s*[:=]|\b(?:sk-|ghp_)[A-Za-z0-9_-]{8,}"
)


def _date(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        parsed = date_type.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be an ISO date")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    cleaned = value.strip()
    if cleaned.startswith(("/", "file://", "\\")) or "/home/" in cleaned:
        raise ValueError(f"{field} contains a private path")
    if _SECRET_PATTERN.search(cleaned):
        raise ValueError(f"{field} contains a secret-like value")
    return cleaned


def _point(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("point must be an object")
    raw_number = value.get("value")
    if isinstance(raw_number, bool) or not isinstance(raw_number, int | float):
        raise ValueError("point value must be a finite number")
    number = float(raw_number)
    if not math.isfinite(number):
        raise ValueError("point value must be finite")
    source_url = _text(value.get("source_url"), "source_url")
    parsed = urlsplit(source_url)
    hostname = parsed.hostname or ""
    private_host = hostname in {"localhost"} or hostname.endswith((".local", ".internal"))
    try:
        private_host = private_host or not ipaddress.ip_address(hostname).is_global
    except ValueError:
        private_host = private_host or "." not in hostname
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or private_host
    ):
        raise ValueError("source_url must be a public HTTPS URL")
    return {
        "label": _text(value.get("label"), "label"),
        "value": number,
        "unit": _text(value.get("unit"), "unit"),
        "observation_date": _date(value.get("observation_date"), "observation_date"),
        "source_label": _text(value.get("source_label"), "source_label"),
        "source_url": source_url,
    }


def _card(key: str, raw: Mapping[str, object]) -> dict[str, object]:
    if raw.get("key") != key:
        raise ValueError(f"invalid chart key: {key}")
    status = raw.get("status")
    if status not in ("ok", "degraded", "missing", "skipped"):
        raise ValueError(f"invalid chart status: {key}")
    raw_points = raw.get("points")
    if not isinstance(raw_points, list):
        raise ValueError(f"chart points must be a list: {key}")
    points = [_point(point) for point in raw_points]
    reason = raw.get("reason")
    if status in ("missing", "skipped"):
        if points:
            raise ValueError(f"{status} chart cannot have points: {key}")
        reason = _text(reason, "reason")
    elif not points:
        raise ValueError(f"{status} chart needs points: {key}")
    elif status == "degraded" or reason is not None:
        reason = _text(reason, "reason")
    return {
        "key": key,
        "title": _text(raw.get("title"), "title"),
        "status": status,
        "reason": reason,
        "points": points,
    }


def build_candidate(
    date: str,
    kind: str,
    cards: Mapping[str, Mapping[str, object]],
    generated_at: str,
) -> dict[str, object]:
    """Whitelist and validate six chart cards; never infer facts from PNG paths."""
    _date(date, "date")
    if kind not in ("morning", "evening"):
        raise ValueError("kind must be morning or evening")
    try:
        generated = datetime.fromisoformat(generated_at)
    except (TypeError, ValueError) as exc:
        raise ValueError("generated_at must include a timezone") from exc
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("generated_at must include a timezone")
    if set(cards) != set(CHART_KEYS):
        raise ValueError("candidate needs exactly six chart keys")

    validated_cards = [_card(key, cards[key]) for key in CHART_KEYS]

    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "publication": "candidate",
        "report_id": f"{date}-{kind}",
        "date": date,
        "kind": kind,
        "generated_at": generated_at,
        "charts": validated_cards,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def write_candidate(path: Path, payload: Mapping[str, object]) -> None:
    """Write a reviewed-shape *candidate* atomically outside the source repo."""
    expected_keys = {
        "schema_version",
        "publication",
        "report_id",
        "date",
        "kind",
        "generated_at",
        "charts",
        "content_sha256",
    }
    if set(payload) != expected_keys or not isinstance(payload.get("charts"), list):
        raise ValueError("candidate payload has unexpected fields")
    raw_cards = cast("list[object]", payload["charts"])
    if len(raw_cards) != len(CHART_KEYS) or any(
        not isinstance(card, Mapping) for card in raw_cards
    ):
        raise ValueError("candidate payload has invalid charts")
    cards = {
        cast("str", cast("Mapping[str, object]", card).get("key")): cast(
            "Mapping[str, object]", card
        )
        for card in raw_cards
    }
    if len(cards) != len(CHART_KEYS):
        raise ValueError("candidate payload has duplicate charts")
    try:
        rebuilt = build_candidate(
            cast("str", payload["date"]),
            cast("str", payload["kind"]),
            cards,
            cast("str", payload["generated_at"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate payload is invalid") from exc
    if rebuilt != payload:
        raise ValueError("candidate payload differs from validated contract")
    destination = path.resolve()
    if destination.is_relative_to(_REPO_ROOT):
        raise ValueError("candidate output must be outside the repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2, allow_nan=False)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
