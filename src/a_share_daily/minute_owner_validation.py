"""Validate minute evidence through the installed data owner's read-only CLI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

RECEIPT_FIELDS = (
    "schema_version",
    "trade_date",
    "partition_path",
    "sidecar_path",
    "partition_sha256",
    "sidecar_sha256",
    "rows",
    "symbols",
    "market_symbol_counts",
    "expected_bars_per_symbol",
    "universe_hash",
    "universe_rule",
    "universe_source",
    "mirror_generated_at",
)


def _check_receipt(payload: Any, root: Path, date: str, exchange: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or any(key not in payload for key in RECEIPT_FIELDS):
        raise ValueError("owner minute receipt is missing required fields")
    if (
        payload.get("validation_schema_version") != "marketdata.minute_exchange_overlay.v1"
        or payload["schema_version"] != "tushare.a_share.minute_partition.promotion.v1"
        or payload["trade_date"] != date
        or payload.get("exchange") != exchange
    ):
        raise ValueError("owner minute receipt schema, date or exchange mismatch")
    counts = payload["market_symbol_counts"]
    if not isinstance(counts, dict) or any(
        type(counts.get(k)) is not int for k in ("SH", "SZ", "BJ")
    ):
        raise ValueError("owner minute receipt has invalid exchange counts")
    if counts[exchange] <= 0 or any(counts[k] != 0 for k in counts if k != exchange):
        raise ValueError("owner minute receipt is empty or contains another exchange")
    symbols, rows, bars = (payload[k] for k in ("symbols", "rows", "expected_bars_per_symbol"))
    if any(type(value) is not int for value in (symbols, rows, bars)) or (
        symbols != counts[exchange] or bars != 241 or rows != symbols * bars
    ):
        raise ValueError("owner minute receipt has inconsistent row counts")
    for key in ("partition_sha256", "sidecar_sha256", "universe_hash"):
        if not isinstance(payload[key], str) or not re.fullmatch(r"[0-9a-f]{64}", payload[key]):
            raise ValueError("owner minute receipt has invalid hash fields")
    partition = root / f"trade_date={date}"
    for key, name in (
        ("partition_path", "part-00000.parquet"),
        ("sidecar_path", "_minute_mirror.json"),
    ):
        if not isinstance(payload[key], str) or Path(payload[key]).resolve() != partition / name:
            raise ValueError("owner minute receipt points outside the requested partition")
    if not isinstance(payload["universe_rule"], str) or not payload["universe_rule"].endswith(
        f":exchange={exchange}"
    ):
        raise ValueError("owner minute receipt has an unexpected universe rule")
    return {key: payload[key] for key in RECEIPT_FIELDS}


def validate_exchange_overlay(
    root: Path, *, trade_date: str, exchange: str, cli: Path | None = None
) -> dict[str, Any]:
    configured = (
        str(cli)
        if cli is not None
        else os.environ.get("MARKETDATA_CLI") or shutil.which("marketdata")
    )
    if not configured:
        raise ValueError("installed data owner CLI is missing; configure MARKETDATA_CLI")
    executable = Path(configured).expanduser()
    if not executable.is_absolute():
        raise ValueError("installed data owner CLI requires an absolute path")
    executable = executable.resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("installed data owner CLI is not executable")
    resolved = root.expanduser().resolve()
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="minute-owner-validation-") as directory:
        try:
            result = subprocess.run(  # noqa: S603 - resolved installed owner CLI, fixed argument shape
                [
                    str(executable),
                    "tushare",
                    "validate-minute-partition",
                    "--data-root",
                    str(resolved),
                    "--trade-date",
                    trade_date,
                    "--exchange",
                    exchange,
                ],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("data owner minute validation could not complete") from exc
    if result.returncode:
        raise ValueError("data owner minute validation rejected the partition")
    try:
        payload = json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        raise ValueError("data owner minute validation returned invalid JSON") from exc
    return _check_receipt(payload, resolved, trade_date, exchange)
