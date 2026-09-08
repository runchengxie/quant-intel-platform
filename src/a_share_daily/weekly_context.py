"""Sidecar freshness contract for the generated weekly market context."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_weekly_context(
    report_path: Path,
    metadata_path: Path,
    report: str,
    *,
    target_trade_date: str,
    actual_through: str | None,
) -> None:
    """Atomically publish report text and a hash-bound freshness sidecar."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "target_trade_date": target_trade_date,
        "actual_through": actual_through,
        "report_sha256": _sha256_text(report),
    }
    _atomic_write(report_path, report)
    _atomic_write(
        metadata_path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def validate_weekly_context(
    report_path: Path,
    metadata_path: Path,
    expected_through: str,
) -> tuple[bool, str]:
    """Validate cutoff and bind the metadata to the exact report body."""
    try:
        report = report_path.read_text(encoding="utf-8")
        payload: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"weekly context artifact unavailable: {exc}"
    if not isinstance(payload, dict):
        return False, "weekly context metadata is not an object"
    if payload.get("schema_version") != SCHEMA_VERSION:
        return False, "weekly context metadata schema mismatch"
    if payload.get("target_trade_date") != expected_through:
        return False, "weekly context target date mismatch"
    if payload.get("actual_through") != expected_through:
        return False, "weekly context actual cutoff mismatch"
    if payload.get("report_sha256") != _sha256_text(report):
        return False, "weekly context report hash mismatch"
    return True, "weekly context is current"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate weekly market context freshness")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--expected-through", required=True)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    valid, reason = validate_weekly_context(
        args.report,
        args.metadata,
        args.expected_through,
    )
    print(reason)
    if not valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
