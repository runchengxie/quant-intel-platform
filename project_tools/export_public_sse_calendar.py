"""Project the owner trade_cal artifact into public SSE session metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def export_calendar(source: Path, output: Path, year: int, source_url: str) -> None:
    """Export dates and open flags only; never publish the private owner rows."""
    frame = pd.read_parquet(source)
    frame = frame[frame["exchange"] == "SSE"]
    dates = pd.to_datetime(frame["cal_date"].astype(str), format="%Y%m%d")
    frame = frame[dates.dt.year == year].copy()
    frame["date"] = dates[dates.dt.year == year].dt.strftime("%Y-%m-%d")
    if frame["date"].duplicated().any() or not frame["is_open"].isin([0, 1]).all():
        raise ValueError("invalid owner SSE calendar")
    payload = {
        "schema_version": "public_sse_calendar.v1",
        "exchange": "SSE",
        "source": "TuShare trade_cal",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_url": source_url,
        "generated_at": datetime.now(UTC).isoformat(),
        "coverage_start": f"{year}-01-01",
        "coverage_end": f"{year}-12-31",
        "days": dict(sorted(zip(frame["date"], frame["is_open"].astype(bool), strict=True))),
    }
    expected = pd.date_range(f"{year}-01-01", f"{year}-12-31").strftime("%Y-%m-%d")
    if set(payload["days"]) != set(expected):
        raise ValueError("owner SSE calendar coverage is incomplete")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--source-url", required=True)
    args = parser.parse_args()
    export_calendar(args.source, args.output, args.year, args.source_url)


if __name__ == "__main__":
    main()
