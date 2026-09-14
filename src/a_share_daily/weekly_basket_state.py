"""Immutable week-scoped freeze state for personal basket delivery."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .weekly_client_basket import _atomic_write


class WeeklyBasketStateError(ValueError):
    """Raised when frozen weekly state is invalid or was modified."""


@dataclass(frozen=True)
class WeeklyBasketLock:
    path: Path
    basket: dict[str, Any]
    report_week: str
    target_hash: str
    revision: int
    reused: bool


def _canonical(payload: Mapping[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeeklyBasketStateError("weekly lock is unreadable") from exc
    expected = hashlib.sha256(_canonical(payload)).hexdigest()
    if payload.get("content_sha256") != expected:
        raise WeeklyBasketStateError("weekly lock was tampered")
    return payload


def _current(root: Path) -> Path | None:
    pointer = root / "current"
    if not pointer.exists():
        return None
    if not pointer.is_symlink():
        raise WeeklyBasketStateError("weekly lock current pointer was tampered")
    path = pointer.resolve() / "lock.json"
    if not path.is_file():
        raise WeeklyBasketStateError("weekly lock current revision is incomplete")
    return path


def acquire_weekly_lock(
    state_root: Path,
    *,
    report_week: str,
    target_hash: str,
    basket: Mapping[str, Any],
    input_hashes: Mapping[str, str],
    override: bool = False,
    override_reason: str | None = None,
) -> WeeklyBasketLock:
    """Freeze the first valid basket for one report week and personal target."""
    root = Path(state_root) / report_week / target_hash
    existing = _current(root)
    if existing is not None and not override:
        payload = _read(existing)
        return WeeklyBasketLock(
            existing,
            dict(payload["basket"]),
            report_week,
            target_hash,
            int(payload["revision"]),
            True,
        )
    if override and not str(override_reason or "").strip():
        raise WeeklyBasketStateError("manual weekly lock override requires a reason")
    revision = int(_read(existing)["revision"]) + 1 if existing else 1
    payload: dict[str, Any] = {
        "schema_version": "a_share_daily.weekly_basket_lock.v1",
        "status": "frozen",
        "report_week": report_week,
        "target_hash": target_hash,
        "revision": revision,
        "basket": dict(basket),
        "input_hashes": dict(input_hashes),
        "override_reason": str(override_reason or ""),
    }
    payload["content_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    revision_root = root / "revisions" / str(revision)
    lock_path = revision_root / "lock.json"
    if revision_root.exists():
        current = _read(lock_path)
        if current != payload:
            raise WeeklyBasketStateError("immutable weekly lock revision was tampered")
    else:
        revision_root.mkdir(parents=True, exist_ok=False)
        _atomic_write(lock_path, json.dumps(payload, ensure_ascii=False, indent=2).encode() + b"\n")
    root.mkdir(parents=True, exist_ok=True)
    pointer = root / "current"
    temporary = root / f".current.{os.getpid()}.tmp"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(os.path.relpath(revision_root, root), target_is_directory=True)
    temporary.replace(pointer)
    return WeeklyBasketLock(lock_path, dict(basket), report_week, target_hash, revision, False)


def load_previous_successful_basket(
    state_root: Path, *, report_week: str, target_hash: str
) -> dict[str, Any] | None:
    """Return the most recent earlier frozen basket for the same target."""
    candidates = []
    for week_root in Path(state_root).glob("????-W??"):
        if week_root.name >= report_week:
            continue
        current = _current(week_root / target_hash)
        if current is not None:
            candidates.append((week_root.name, current))
    if not candidates:
        return None
    return dict(_read(max(candidates)[1])["basket"])


__all__ = [
    "WeeklyBasketLock",
    "WeeklyBasketStateError",
    "acquire_weekly_lock",
    "load_previous_successful_basket",
]
