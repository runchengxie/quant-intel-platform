"""Unified CLI for TuShare data jobs.

Usage:
    marketops tushare daily-refresh
    marketops tushare stock-st fetch
    marketops tushare stock-st backfill
    marketops tushare stock-st check-zero
    marketops tushare index-weight refresh [--code ...]
    marketops tushare listed-company fetch [--datasets ...]
    marketops tushare listed-company backfill [--datasets ...]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ops_common.env import load_local_env

from .client import init_tushare
from .constants import (
    ALL_LISTED_COMPANY_DATASETS,
    DATASET_SHARE_FLOAT,
    DATASET_STK_MANAGERS,
    DEDUP_KEYS,
    DEFAULT_EXCHANGES,
    DEFAULT_INDEX_CODES,
    DEFAULT_INDEX_START_DATE,
    DEFAULT_MANAGERS_WINDOW,
    DEFAULT_SHARE_FLOAT_THRESHOLD,
    DEFAULT_SHARE_FLOAT_WINDOW,
    DEFAULT_YEARS,
)
from .index_weight import refresh_index_weight
from .listed_company import ListedCompanyFetcher
from .retry import FetchRunner, RateLimiter
from .stock_st import backfill_stock_st, check_zero_row_files, fetch_stock_st
from .storage import DataStore, ReferenceAssetUnavailable, load_mdp_asset
from .windowing import format_yyyymmdd, resolve_date_range

BJT = ZoneInfo("Asia/Shanghai")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "tushare"


def _parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_datasets(raw: str | None) -> list[str]:
    if not raw:
        return list(ALL_LISTED_COMPANY_DATASETS)
    datasets = _parse_csv_list(raw)
    invalid = sorted(set(datasets) - set(ALL_LISTED_COMPANY_DATASETS))
    if invalid:
        raise SystemExit(f"Unsupported dataset(s): {', '.join(invalid)}")
    return datasets


def _parse_exchanges(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_EXCHANGES
    return tuple(_parse_csv_list(raw))


def _parse_index_codes(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_INDEX_CODES)
    return [code.strip() for code in raw.split(",") if code.strip()]


def cmd_stock_st_fetch(args: argparse.Namespace) -> int:
    trade_date = args.trade_date or datetime.now(tz=BJT).strftime("%Y%m%d")
    frame, _ = load_mdp_asset("stock_st")
    if "trade_date" not in frame.columns:
        raise ReferenceAssetUnavailable("MDP stock_st asset lacks 'trade_date'")
    dates = frame["trade_date"].astype(str).str.replace("-", "", regex=False)
    eligible = dates[dates <= trade_date]
    if eligible.empty:
        raise ReferenceAssetUnavailable(f"MDP stock_st asset has no date on or before {trade_date}")
    normalized = str(eligible.max())
    if normalized != trade_date:
        print(f"TRADE_DATE {trade_date} 非可用日期，使用最近资产日期 {normalized}")
    result = fetch_stock_st(None, trade_date=normalized, data_dir=Path(args.data_dir))
    print(f"stock_st: {result.rows} rows -> {result.path}")
    return 0


def cmd_stock_st_backfill(args: argparse.Namespace) -> int:
    today = datetime.now(tz=BJT).date()
    start = date(2016, 1, 1)
    end = today
    results = backfill_stock_st(None, start=start, end=end, data_dir=Path(args.data_dir))
    total_rows = sum(r.rows for r in results)
    print(f"\nBackfill complete: {len(results)} files, {total_rows} total rows")
    return 0


def cmd_stock_st_check_zero(args: argparse.Namespace) -> int:
    zero = check_zero_row_files(Path(args.data_dir))
    return 1 if zero else 0


def cmd_index_weight_refresh(args: argparse.Namespace) -> int:
    today_str = datetime.now(tz=BJT).strftime("%Y%m%d")
    end_date = args.end_date or today_str
    index_start = args.start_date or DEFAULT_INDEX_START_DATE
    codes = _parse_index_codes(args.codes)

    all_results = []
    for code in codes:
        results = refresh_index_weight(
            None,
            index_code=code,
            data_dir=Path(args.data_dir),
            default_start=index_start,
            end_date=end_date,
            force_full_refresh=args.force_full_refresh,
            generate_daily=not args.no_daily,
            generate_drift=not args.no_drift,
        )
        all_results.extend(results)

    print(f"\nRefresh complete: {len(all_results)} outputs")
    for r in all_results:
        print(f"  - {r.label}: {r.rows} rows -> {r.path}")
    return 0


def _save_consolidated(store: DataStore, dataset: str) -> tuple[int, Path | None]:
    df = store.consolidate(dataset, DEDUP_KEYS.get(dataset, []))
    if df.empty:
        return 0, None
    path = store.save_curated(dataset, df)
    return len(df), path


def _resolve_rpm(args: argparse.Namespace) -> float:
    """Pick requests-per-minute from CLI flag, env, or the 200 default."""
    if args.rpm is not None:
        return args.rpm
    rpm_env = os.getenv("TUSHARE_RPM", "").strip()
    if rpm_env:
        try:
            return float(rpm_env)
        except ValueError:
            return 200.0
    return 200.0


def _fetch_requested_datasets(
    fetcher: ListedCompanyFetcher,
    datasets: list[str],
    args: argparse.Namespace,
    start_dt: date | None,
    end_dt: date | None,
) -> list:
    """Run each requested dataset's fetcher and collect its summary."""
    summaries = []
    if "stock_basic" in datasets:
        summaries.append(fetcher.fetch_stock_basic(list_status=args.list_status))
    if "stock_company" in datasets:
        summaries.append(fetcher.fetch_stock_company(exchanges=_parse_exchanges(args.exchanges)))
    if DATASET_STK_MANAGERS in datasets and start_dt and end_dt:
        summaries.append(
            fetcher.fetch_stk_managers(
                start_dt,
                end_dt,
                window=args.managers_window,
                resume=args.resume,
                force=args.force,
            )
        )
    if DATASET_SHARE_FLOAT in datasets and start_dt and end_dt:
        summaries.append(
            fetcher.fetch_share_float(
                start_dt,
                end_dt,
                window=args.share_float_window,
                resume=args.resume,
                force=args.force,
                threshold=args.share_float_threshold,
            )
        )
    return summaries


def _print_consolidated_outputs(store: DataStore, datasets: list[str], consolidate: bool) -> None:
    """Emit consolidated and curated paths for the two event-range datasets."""
    if not consolidate:
        return
    for dataset in (DATASET_STK_MANAGERS, DATASET_SHARE_FLOAT):
        if dataset not in datasets:
            continue
        rows, path = _save_consolidated(store, dataset)
        if path:
            print(f"- consolidated {dataset}: rows={rows} path={path}")
        curated = store.curated_path(dataset)
        if curated.exists():
            print(f"- curated output: {curated}")


def cmd_listed_company_fetch(args: argparse.Namespace) -> int:
    load_local_env()
    datasets = _parse_datasets(args.datasets)
    pro = init_tushare(args.token or None) if "stock_basic" in datasets else None

    needs_event_range = DATASET_STK_MANAGERS in datasets or DATASET_SHARE_FLOAT in datasets
    if needs_event_range:
        start_dt, end_dt = resolve_date_range(
            args.start_date, args.end_date, args.years, default_years=DEFAULT_YEARS
        )
    else:
        start_dt = end_dt = None

    rpm = _resolve_rpm(args)
    min_interval = 60.0 / rpm if rpm > 0 else 0.0

    store = DataStore(base_dir=Path(args.data_dir), file_format=args.format)
    runner = FetchRunner(
        rate_limiter=RateLimiter(min_interval=min_interval),
        retries=args.retries,
        base_delay=args.base_delay,
        max_delay=args.max_delay,
    )
    fetcher = ListedCompanyFetcher(pro, runner, store)

    summaries = _fetch_requested_datasets(fetcher, datasets, args, start_dt, end_dt)

    _print_consolidated_outputs(store, datasets, args.consolidate)

    print("\nFetch complete:")
    for summary in summaries:
        print(
            f"- {summary.dataset}: windows={summary.windows} rows={summary.rows} files={summary.files}"
        )
    if start_dt and end_dt:
        print(f"Event date range: {format_yyyymmdd(start_dt)} -> {format_yyyymmdd(end_dt)}")

    if args.consolidate:
        for dataset in (DATASET_STK_MANAGERS, DATASET_SHARE_FLOAT):
            if dataset in datasets:
                curated = store.curated_path(dataset)
                if curated.exists():
                    print(f"- curated output: {curated}")

    return 0


def cmd_listed_company_backfill(args: argparse.Namespace) -> int:
    """Alias for fetch with --force --resume."""
    args.force = True
    args.resume = True
    return cmd_listed_company_fetch(args)


def cmd_daily_refresh(args: argparse.Namespace) -> int:
    """Run stock_st + index_weight refresh in one go — the daily cron path."""
    exit_code = 0

    # 1) stock_st
    print("=== stock_st ===")
    try:
        ec = cmd_stock_st_fetch(args)
        if ec != 0:
            exit_code = ec
    except SystemExit as e:
        print(f"stock_st failed: {e}")
        exit_code = 1

    # 2) index_weight for all default codes
    print("\n=== index_weight ===")
    try:
        ec = cmd_index_weight_refresh(args)
        if ec != 0:
            exit_code = ec
    except SystemExit as e:
        print(f"index_weight failed: {e}")
        exit_code = 1

    return exit_code


def _add_daily_refresh_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--token", default="", help="TuShare token")
    p.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    p.add_argument("--trade-date", help="Override trade_date (YYYYMMDD)")
    p.add_argument("--codes", help="Comma-separated index codes")
    p.add_argument("--start-date", help="Index start date (YYYYMMDD)")
    p.add_argument("--end-date", help="Index end date (YYYYMMDD)")
    p.add_argument("--force-full-refresh", action="store_true")
    p.add_argument("--no-daily", action="store_true", help="Skip daily expansion")
    p.add_argument("--no-drift", action="store_true", help="Skip drift weights")


def _add_stock_st_args(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("stock-st", help="ST stock list operations")
    ss = p.add_subparsers(dest="stock_st_command", required=True)

    fetch_ss = ss.add_parser("fetch", help="Fetch stock_st for a single date")
    fetch_ss.add_argument("--token", default="")
    fetch_ss.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    fetch_ss.add_argument("--trade-date", help="Trade date (YYYYMMDD, default: today)")

    backfill_ss = ss.add_parser("backfill", help="Backfill stock_st for all trading days")
    backfill_ss.add_argument("--token", default="")
    backfill_ss.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))

    check_ss = ss.add_parser("check-zero", help="Check for zero-row stock_st files")
    check_ss.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))


def _add_index_weight_args(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("index-weight", help="Index weight operations")
    iw = p.add_subparsers(dest="iw_command", required=True)

    refresh_iw = iw.add_parser("refresh", help="Refresh index weight data")
    refresh_iw.add_argument("--token", default="")
    refresh_iw.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    refresh_iw.add_argument("--codes", help="Comma-separated index codes")
    refresh_iw.add_argument("--start-date", help="Index start date (YYYYMMDD)")
    refresh_iw.add_argument("--end-date", help="Index end date (YYYYMMDD)")
    refresh_iw.add_argument("--force-full-refresh", action="store_true")
    refresh_iw.add_argument("--no-daily", action="store_true")
    refresh_iw.add_argument("--no-drift", action="store_true")


def _add_listed_company_args(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("listed-company", help="Listed company data operations")
    lc = p.add_subparsers(dest="lc_command", required=True)

    fetch_lc = lc.add_parser("fetch", help="Fetch listed company datasets")
    fetch_lc.add_argument("--token", default="")
    fetch_lc.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    fetch_lc.add_argument(
        "--datasets",
        default=None,
        help=f"Comma-separated (default: {', '.join(ALL_LISTED_COMPANY_DATASETS)})",
    )
    fetch_lc.add_argument("--format", choices=["csv", "parquet"], default="csv")
    fetch_lc.add_argument("--list-status", default="", help="stock_basic list_status (L/D/P)")
    fetch_lc.add_argument("--exchanges", default=None, help="Comma-separated exchanges")
    fetch_lc.add_argument("--start-date", default=None, help="Event start date (YYYYMMDD)")
    fetch_lc.add_argument("--end-date", default=None, help="Event end date (YYYYMMDD)")
    fetch_lc.add_argument(
        "--years",
        type=int,
        default=None,
        help=f"Lookback years (default: {DEFAULT_YEARS})",
    )
    fetch_lc.add_argument(
        "--managers-window",
        choices=["day", "week", "month"],
        default=DEFAULT_MANAGERS_WINDOW,
    )
    fetch_lc.add_argument(
        "--share-float-window",
        choices=["day", "week", "month"],
        default=DEFAULT_SHARE_FLOAT_WINDOW,
    )
    fetch_lc.add_argument(
        "--share-float-threshold", type=int, default=DEFAULT_SHARE_FLOAT_THRESHOLD
    )
    fetch_lc.add_argument("--resume", action="store_true")
    fetch_lc.add_argument("--force", action="store_true")
    fetch_lc.add_argument("--consolidate", action="store_true")
    fetch_lc.add_argument("--rpm", type=float, default=None)
    fetch_lc.add_argument("--retries", type=int, default=6)
    fetch_lc.add_argument("--base-delay", type=float, default=2.0)
    fetch_lc.add_argument("--max-delay", type=float, default=60.0)

    backfill_lc = lc.add_parser(
        "backfill", help="Force backfill (alias for fetch --force --resume)"
    )
    backfill_lc.add_argument("--token", default="")
    backfill_lc.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    backfill_lc.add_argument("--datasets", default=None)
    backfill_lc.add_argument("--format", choices=["csv", "parquet"], default="csv")
    backfill_lc.add_argument("--list-status", default="")
    backfill_lc.add_argument("--exchanges", default=None)
    backfill_lc.add_argument("--start-date", default=None)
    backfill_lc.add_argument("--end-date", default=None)
    backfill_lc.add_argument("--years", type=int, default=None)
    backfill_lc.add_argument(
        "--managers-window",
        choices=["day", "week", "month"],
        default=DEFAULT_MANAGERS_WINDOW,
    )
    backfill_lc.add_argument(
        "--share-float-window",
        choices=["day", "week", "month"],
        default=DEFAULT_SHARE_FLOAT_WINDOW,
    )
    backfill_lc.add_argument(
        "--share-float-threshold", type=int, default=DEFAULT_SHARE_FLOAT_THRESHOLD
    )
    backfill_lc.add_argument("--consolidate", action="store_true")
    backfill_lc.add_argument("--rpm", type=float, default=None)
    backfill_lc.add_argument("--retries", type=int, default=6)
    backfill_lc.add_argument("--base-delay", type=float, default=2.0)
    backfill_lc.add_argument("--max-delay", type=float, default=60.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marketops", description="Market operations CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- tushare ---
    tushare_parser = subparsers.add_parser("tushare", help="TuShare data jobs")
    tushare_sub = tushare_parser.add_subparsers(dest="tushare_command", required=True)

    _add_daily_refresh_args(
        tushare_sub.add_parser("daily-refresh", help="Run stock_st + index_weight daily refresh")
    )
    _add_stock_st_args(tushare_sub)
    _add_index_weight_args(tushare_sub)
    _add_listed_company_args(tushare_sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # top-level routing
    if args.command == "tushare":
        if args.tushare_command == "daily-refresh":
            return cmd_daily_refresh(args)
        if args.tushare_command == "stock-st":
            if args.stock_st_command == "fetch":
                return cmd_stock_st_fetch(args)
            if args.stock_st_command == "backfill":
                return cmd_stock_st_backfill(args)
            if args.stock_st_command == "check-zero":
                return cmd_stock_st_check_zero(args)
        if args.tushare_command == "index-weight" and args.iw_command == "refresh":
            return cmd_index_weight_refresh(args)
        if args.tushare_command == "listed-company":
            if args.lc_command == "fetch":
                return cmd_listed_company_fetch(args)
            if args.lc_command == "backfill":
                return cmd_listed_company_backfill(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
