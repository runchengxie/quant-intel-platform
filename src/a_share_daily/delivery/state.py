"""Delivery idempotency, artifact bookkeeping and status persistence.

Moved verbatim from ``report_delivery.py`` as a pure physical refactor.
All symbols here are re-exported from ``report_delivery`` to keep callers
and tests working unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from a_share_daily.delivery.io_util import PROJECT_ROOT
from a_share_daily.delivery.targets import _redact_target


def _idempotency_key(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()[:32]


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _artifact_entry(path: Path, *, role: str) -> dict[str, Any]:
    resolved = path.expanduser()
    entry: dict[str, Any] = {
        "role": role,
        "path": str(resolved),
        "exists": resolved.exists(),
    }
    if resolved.exists():
        try:
            stat = resolved.stat()
            entry.update(
                {
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "sha256": _sha256_file(resolved),
                }
            )
        except OSError:
            entry["exists"] = False
    return entry


def _delivery_state_dir() -> Path:
    return Path(
        os.environ.get(
            "A_SHARE_DELIVERY_STATE_DIR",
            str(PROJECT_ROOT / "state" / "a_share_daily_delivery"),
        )
    ).expanduser()


def _write_delivery_status(
    *,
    kind: str,
    trade_date: str,
    mode: str,
    success: bool,
    routes: Mapping[str, Any],
    artifacts: Sequence[dict[str, Any]],
    lark_targets: Sequence[str],
    hermes_targets: Sequence[str],
) -> None:
    state_dir = _delivery_state_dir()
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        payload = {
            "kind": kind,
            "trade_date": trade_date,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "success": success,
            "routes": dict(routes),
            "targets": {
                "lark": list(lark_targets),
                "hermes": [_redact_target(target) for target in hermes_targets],
                "lark_count": len(lark_targets),
                "hermes_count": len(hermes_targets),
            },
            "artifacts": list(artifacts),
        }
        output = state_dir / f"{kind}_{trade_date}_{timestamp}.json"
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        latest = state_dir / f"{kind}_latest.json"
        latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[report_delivery] failed to write delivery status: {exc}", file=sys.stderr)
