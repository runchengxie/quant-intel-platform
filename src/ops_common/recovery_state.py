"""Persistence and attempt bookkeeping for scheduled recovery.

The recovery coordinator keeps these small, deterministic helpers separate so
the orchestration code can focus on stage ordering and policy decisions.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol


class RecoverySpecLike(Protocol):
    key: str
    dependencies: tuple[str, ...]
    report_kind: str | None


def read_state(path: Path, date_key: str) -> dict[str, Any]:
    """Read a date-scoped receipt, returning an empty mapping when invalid."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("date") != date_key:
        return {}
    return payload


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Replace a JSON file atomically, cleaning up a failed temporary write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def failure_fingerprint(
    stages: Sequence[Mapping[str, Any]],
    *,
    alertable_statuses: frozenset[str],
) -> str | None:
    failures = [
        {
            "key": stage.get("key"),
            "status": "unhealthy",
            "target_date": stage.get("target_date"),
            "detail": stage.get("detail") or stage.get("initial_freshness", {}).get("detail"),
        }
        for stage in stages
        if stage.get("status") in alertable_statuses
    ]
    if not failures:
        return None
    encoded = json.dumps(failures, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def disabled_stage_statuses(
    specs: Sequence[RecoverySpecLike], requested: Sequence[str]
) -> dict[str, str]:
    """Return configured disabled stages and every downstream dependent."""
    known = {spec.key for spec in specs}
    unknown = set(requested) - known
    if unknown:
        raise ValueError(f"unknown disabled recovery stage(s): {', '.join(sorted(unknown))}")
    disabled = dict.fromkeys(requested, "disabled_by_configuration")
    changed = True
    while changed:
        changed = False
        for spec in specs:
            if spec.key not in disabled and any(key in disabled for key in spec.dependencies):
                disabled[spec.key] = "disabled_dependency"
                changed = True
    return disabled


def recent_attempt(attempts: Sequence[Mapping[str, Any]], now: datetime, cooldown: int) -> bool:
    if not attempts:
        return False
    value = attempts[-1].get("started_at")
    if not isinstance(value, str):
        return False
    try:
        started = datetime.fromisoformat(value)
    except ValueError:
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return now.astimezone(UTC) - started.astimezone(UTC) < timedelta(minutes=cooldown)


def successful_delivery_attempt(
    attempts: Sequence[Mapping[str, Any]], *, target_date: str, report_mode: str
) -> bool:
    return any(
        attempt.get("returncode") == 0
        and attempt.get("target_date") == target_date
        and attempt.get("report_mode") == report_mode
        for attempt in attempts
    )


def budget_attempts(
    attempts: Sequence[Mapping[str, Any]],
    *,
    report_kind: str | None,
    target_date: str,
    report_mode: str,
) -> list[Mapping[str, Any]]:
    if report_kind is None:
        return [
            attempt for attempt in attempts if attempt.get("target_date") in {None, target_date}
        ]
    return [
        attempt
        for attempt in attempts
        if attempt.get("target_date") == target_date and attempt.get("report_mode") == report_mode
    ]


def previous_attempts(path: Path, date_key: str) -> dict[str, list[dict[str, Any]]]:
    previous = read_state(path, date_key)
    payload = previous.get("attempts")
    if not isinstance(payload, dict):
        return {}
    attempts: dict[str, list[dict[str, Any]]] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, list):
            attempts[key] = [dict(item) for item in value if isinstance(item, Mapping)]
    return attempts
