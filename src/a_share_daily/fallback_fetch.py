#!/usr/bin/env python3
"""Cross-market data fallback fetcher.

Reads from GH Actions data-snapshots/ when available. When the snapshot is
missing or stale, runs live fetch (yfinance/FRED/AAII) and writes the result
back to data-snapshots/ so downstream consumers don't need to know whether
GH Actions ran or not.

Usage:
    uv run python src/a_share_daily/fallback_fetch.py              # today
    uv run python src/a_share_daily/fallback_fetch.py --date 20260629
    uv run python src/a_share_daily/fallback_fetch.py --json       # JSON output
    CROSS_MARKET_FORCE_LIVE=1 ...                                  # force live fetch

Exit codes: 0=OK, 1=partial data (some fetchers failed), 2=total failure
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_ROOT = Path(
    os.environ.get("CROSS_MARKET_SNAPSHOT_ROOT", str(PROJECT_ROOT / "data-snapshots"))
).expanduser()
SNAPSHOT_DIR = SNAPSHOT_ROOT / "cross-market"
LATEST_DIR = SNAPSHOT_ROOT / "latest"


def _snapshot_dirs() -> tuple[Path, Path]:
    """Resolve write locations at call time so late env loading cannot split I/O."""
    configured = os.environ.get("CROSS_MARKET_SNAPSHOT_ROOT", "").strip()
    if configured:
        root = Path(configured).expanduser()
        return root / "cross-market", root / "latest"
    return SNAPSHOT_DIR, LATEST_DIR


def _ensure_dirs() -> None:
    snapshot_dir, latest_dir = _snapshot_dirs()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)


def _write_snapshot(data: dict, trade_date: str) -> Path:
    """Write snapshot JSON to data-snapshots/ (mirrors GH Actions layout)."""
    snapshot_dir, latest_dir = _snapshot_dirs()
    _ensure_dirs()
    date_dash = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

    # Date-specific snapshot
    date_path = snapshot_dir / f"{date_dash}.json"
    date_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Latest symlink target (also a copy, not a symlink)
    latest_path = latest_dir / "cross_market_snapshot.json"
    latest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return date_path


def _summary(data: dict) -> str:
    """One-line status summary."""
    us_ok = sum(
        1 for v in data.get("us_stocks", {}).values() if isinstance(v, dict) and "close" in v
    )
    us_total = len(data.get("us_stocks", {}))
    comm_ok = sum(
        1 for v in data.get("commodities", {}).values() if isinstance(v, dict) and "close" in v
    )
    macro_ok = sum(
        1 for v in data.get("macros", {}).values() if isinstance(v, dict) and "close" in v
    )
    source = data.get("_source", "live")
    errors = data.get("errors", [])
    freshness_warnings = data.get("_freshness_warnings", [])
    return (
        f"[{source}] date={data.get('date')} "
        f"us={us_ok}/{us_total} comm={comm_ok} macro={macro_ok} "
        f"errors={len(errors)} freshness_warnings={len(freshness_warnings)}"
    )


def run(trade_date: str, force_live: bool = False) -> dict:
    """Fetch cross-market data with snapshot-first fallback.

    Returns the data dict. Writes to data-snapshots/ if live fetch was used.
    """
    from a_share_daily.cross_market import _load_snapshot
    from a_share_daily.cross_market import run as live_run

    # Try snapshot first (unless forced)
    if not force_live:
        snapshot = _load_snapshot(trade_date)
        if snapshot is not None and snapshot.get("date") == trade_date:
            if not snapshot.get("_freshness_warnings"):
                print(f"[snapshot] {_summary(snapshot)}", file=sys.stderr)
                return snapshot
            print(f"[snapshot-stale] {_summary(snapshot)}; trying live fetch", file=sys.stderr)
        elif snapshot is not None:
            print(
                f"[snapshot-stale] snapshot date={snapshot.get('date')} "
                f"does not match requested date={trade_date}; trying live fetch",
                file=sys.stderr,
            )

    # Live fetch
    print(f"[live] Fetching cross-market data for {trade_date} ...", file=sys.stderr)

    if force_live:
        os.environ["CROSS_MARKET_FORCE_LIVE"] = "1"

    data = live_run(trade_date)
    data["_source"] = "local-fallback"

    # Write back to data-snapshots so downstream consumers see it
    path = _write_snapshot(data, trade_date)
    print(f"[save] Wrote snapshot to {path}", file=sys.stderr)
    print(f"[live] {_summary(data)}", file=sys.stderr)

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-market data fallback fetcher")
    parser.add_argument("--date", help="Trade date YYYYMMDD (default: today)")
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    parser.add_argument("--force", action="store_true", help="Force live fetch, skip snapshot")
    args = parser.parse_args()

    trade_date = args.date or datetime.now().strftime("%Y%m%d")

    try:
        data = run(trade_date, force_live=args.force)
    except Exception as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_summary(data))

    # Exit code based on data quality
    errors = data.get("errors", [])
    if errors:
        return 1  # Partial data
    return 0


if __name__ == "__main__":
    sys.exit(main())
