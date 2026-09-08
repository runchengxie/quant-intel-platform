"""Local A-share trading-calendar checks for scheduled report guards."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq

NON_TRADING_DAY_EXIT = 20
MAX_LOOKBACK_OPEN_DAYS = 10


class TradingCalendarError(RuntimeError):
    """Raised when a local trading calendar cannot answer the requested date."""


def normalize_calendar_date(value: str) -> str:
    """Return a validated ``YYYYMMDD`` calendar date."""
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise TradingCalendarError(f"invalid calendar date {value!r}; expected YYYYMMDD") from exc


def is_open_trading_day(calendar_path: Path, target_date: str) -> bool:
    """Return whether *target_date* is open according to a local TuShare calendar."""
    target = normalize_calendar_date(target_date)
    if not calendar_path.is_file():
        raise TradingCalendarError(f"trade calendar not found: {calendar_path}")

    try:
        payload = pq.read_table(
            calendar_path,
            columns=["cal_date", "is_open"],
            filters=[("cal_date", "=", target)],
        ).to_pydict()
    except Exception as exc:
        raise TradingCalendarError(f"failed to read trade calendar {calendar_path}: {exc}") from exc

    flags = {
        int(open_flag)
        for date, open_flag in zip(payload["cal_date"], payload["is_open"], strict=False)
        if str(date) == target
    }
    if not flags:
        raise TradingCalendarError(f"{target} is missing from trade calendar: {calendar_path}")
    if not flags <= {0, 1} or len(flags) != 1:
        raise TradingCalendarError(
            f"{target} has inconsistent is_open values in trade calendar: {sorted(flags)}"
        )
    return flags == {1}


def recent_open_trading_dates(
    calendar_path: Path,
    target_date: str,
    count: int,
) -> tuple[str, ...]:
    """Return the last *count* open dates ending on or before *target_date*."""
    target = normalize_calendar_date(target_date)
    if count < 1:
        raise TradingCalendarError("count must be at least 1")
    if count > MAX_LOOKBACK_OPEN_DAYS:
        raise TradingCalendarError(f"count must not exceed {MAX_LOOKBACK_OPEN_DAYS}")
    if not calendar_path.is_file():
        raise TradingCalendarError(f"trade calendar not found: {calendar_path}")

    # A stale calendar must not silently turn an N-session lookback into a much
    # wider provider request. This also validates duplicate target rows before
    # the range query below.
    is_open_trading_day(calendar_path, target)

    try:
        payload = pq.read_table(
            calendar_path,
            columns=["cal_date", "is_open"],
            filters=[("cal_date", "<=", target), ("is_open", "=", 1)],
        ).to_pydict()
    except Exception as exc:
        raise TradingCalendarError(f"failed to read trade calendar {calendar_path}: {exc}") from exc

    dates = sorted(
        {
            str(date)
            for date, open_flag in zip(payload["cal_date"], payload["is_open"], strict=False)
            if int(open_flag) == 1 and str(date) <= target
        }
    )
    if len(dates) < count:
        raise TradingCalendarError(
            f"trade calendar has only {len(dates)} open dates on or before {target}; need {count}"
        )
    return tuple(dates[-count:])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a date in the local A-share calendar")
    parser.add_argument("--date", required=True, help="Calendar date in YYYYMMDD format")
    parser.add_argument("--calendar", required=True, type=Path, help="TuShare trade_cal parquet")
    parser.add_argument(
        "--lookback-open-days",
        type=int,
        help="Print the first date in the trailing N-open-day window and exit",
    )
    parser.add_argument(
        "--lookback-output",
        choices=("start", "csv"),
        default="start",
        help="Choose whether a lookback prints its first date or every date as CSV",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback_open_days is not None:
        try:
            dates = recent_open_trading_dates(
                args.calendar,
                args.date,
                args.lookback_open_days,
            )
        except TradingCalendarError as exc:
            print(f"[trading-calendar] [ERROR] {exc}", file=sys.stderr)
            return 1
        print(",".join(dates) if args.lookback_output == "csv" else dates[0])
        return 0

    try:
        is_open = is_open_trading_day(args.calendar, args.date)
    except TradingCalendarError as exc:
        print(f"[trading-calendar] [ERROR] {exc}", file=sys.stderr)
        return 1

    if not is_open:
        print(f"[trading-calendar] {args.date} is not an open A-share trading day")
        return NON_TRADING_DAY_EXIT

    print(f"[trading-calendar] {args.date} is an open A-share trading day")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
