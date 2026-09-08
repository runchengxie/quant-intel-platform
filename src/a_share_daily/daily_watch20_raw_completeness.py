"""Publish the raw-minute completeness receipt used by DailyWatch20 recovery.

This is operational glue for the report scheduler. Research factor expansion and
Top200 observation ownership live in research-workspace and deliberately do not
share this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1
QUOTA_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _date_key(value: str) -> str:
    resolved = str(value).strip().replace("-", "")
    if len(resolved) != 8 or not resolved.isdigit():
        raise ValueError("trade date must use YYYYMMDD")
    datetime.strptime(resolved, "%Y%m%d")
    return resolved


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read completeness evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"completeness evidence must be a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _quota_date(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("completion timestamp must be timezone-aware")
    return now.astimezone(QUOTA_TIMEZONE).strftime("%Y%m%d")


def _write_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_exchange_overlay(root: Path, *, trade_date: str, exchange: str) -> dict[str, Any]:
    from market_data_platform.providers.tushare_a_share_mins import (
        UNIVERSE_RULE,
        validate_complete_minute_partition,
    )

    receipt = validate_complete_minute_partition(
        root / f"trade_date={trade_date}",
        trade_date=trade_date,
        require_full_universe=False,
    )
    expected_rule = f"{UNIVERSE_RULE}:exchange={exchange}"
    if receipt.get("universe_rule") != expected_rule:
        raise ValueError(
            f"{exchange} minute overlay uses unexpected universe rule: "
            f"{receipt.get('universe_rule')!r}"
        )
    counts = receipt.get("market_symbol_counts")
    if not isinstance(counts, dict) or int(counts.get(exchange, 0)) <= 0:
        raise ValueError(f"{exchange} minute overlay contains no {exchange} symbols")
    if any(int(counts.get(market, 0)) != 0 for market in {"SH", "SZ", "BJ"} - {exchange}):
        raise ValueError(f"{exchange} minute overlay contains out-of-scope symbols")
    return {
        key: receipt[key]
        for key in (
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
    }


def publish_daily_watch_receipt(
    *,
    freshness_path: Path,
    trade_date: str,
    marker_root: Path,
    overlay_roots: dict[str, Path] | None = None,
    now: datetime | None = None,
) -> Path:
    """Validate exact-date minute evidence independently of other input gates."""

    resolved_date = _date_key(trade_date)
    freshness = _load_object(freshness_path)
    required_date = _date_key(str(freshness.get("required_minute_date") or ""))
    if required_date != resolved_date:
        raise ValueError(
            f"DailyWatch minute date mismatch: expected={resolved_date} actual={required_date}"
        )
    if freshness.get("status") not in {"ready", "unavailable"}:
        raise ValueError("DailyWatch freshness report has an invalid status")
    minute_source = freshness.get("minute_source")
    if minute_source not in {"canonical", "tushare_operational", "tushare_sh_sz_overlay"}:
        raise ValueError("DailyWatch freshness report has no complete minute source")

    partition_receipts: dict[str, dict[str, Any]] = {}
    if minute_source == "tushare_sh_sz_overlay":
        roots = overlay_roots or {}
        missing = sorted({"SH", "SZ"} - set(roots))
        if missing:
            raise ValueError(f"DailyWatch overlay roots are missing: {missing}")
        partition_receipts = {
            exchange: _validate_exchange_overlay(
                roots[exchange], trade_date=resolved_date, exchange=exchange
            )
            for exchange in ("SH", "SZ")
        }

    instant = now or datetime.now(UTC)
    quota_date = _quota_date(instant)
    durable_evidence = marker_root / quota_date / "evidence" / "daily_watch20_freshness.json"
    _write_atomic_json(
        durable_evidence,
        {
            "freshness": freshness,
            "minute_source": minute_source,
            "partition_receipts": partition_receipts,
        },
    )
    evidence_sha = _sha256(durable_evidence)
    marker = marker_root / quota_date / "daily_watch20.json"
    _write_atomic_json(
        marker,
        {
            "schema_version": SCHEMA_VERSION,
            "raw_complete": True,
            "quota_date": quota_date,
            "quota_timezone": str(QUOTA_TIMEZONE),
            "consumer": "daily_watch20",
            "trade_date": resolved_date,
            "completed_at": instant.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "evidence_path": str(durable_evidence.resolve()),
            "evidence_sha256": evidence_sha,
            "evidence": {
                "kind": "daily_watch20_input_freshness",
                "path": str(durable_evidence.resolve()),
                "sha256": evidence_sha,
                "minute_source": minute_source,
                "source_date": freshness.get("source_date"),
                "signal_date": freshness.get("signal_date"),
                "partition_receipts": partition_receipts,
            },
        },
    )
    return marker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker-root", required=True)
    parser.add_argument("--freshness-json", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--minute-overlay-sh-root")
    parser.add_argument("--minute-overlay-sz-root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    overlay_roots = {
        exchange: Path(value).expanduser().resolve()
        for exchange, value in (
            ("SH", args.minute_overlay_sh_root),
            ("SZ", args.minute_overlay_sz_root),
        )
        if value
    }
    marker = publish_daily_watch_receipt(
        freshness_path=Path(args.freshness_json).expanduser().resolve(),
        trade_date=args.trade_date,
        marker_root=Path(args.marker_root).expanduser().resolve(),
        overlay_roots=overlay_roots,
    )
    print(marker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
