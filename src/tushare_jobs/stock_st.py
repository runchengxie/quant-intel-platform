"""Compatibility export for MDP-owned ST (special treatment) reference data."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .retry import FetchRunner
from .storage import ReferenceAssetUnavailable, load_mdp_asset


@dataclass
class FetchResult:
    label: str
    path: Path
    rows: int


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def has_data_rows(path: Path) -> bool:
    """Return True if file exists and has at least one data row beyond the header."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with path.open(newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            return next(reader, None) is not None
    except OSError as exc:
        print(f"读取 {path} 失败，视为缺失：{exc}")
        return False


def _extract_trade_date_from_path(path: Path) -> date | None:
    stem = path.stem
    if "_" not in stem:
        return None
    candidate = stem.split("_")[-1]
    try:
        return datetime.strptime(candidate, "%Y%m%d").date()
    except ValueError:
        return None


def fetch_stock_st(
    pro, trade_date: str, *, data_dir: Path, runner: FetchRunner | None = None
) -> FetchResult:
    """Export one trade date from the published MDP ``stock_st`` asset."""
    mdp_df, mdp_path = load_mdp_asset("stock_st")
    col = "trade_date"
    if col not in mdp_df.columns:
        raise ReferenceAssetUnavailable(f"MDP stock_st asset lacks {col!r}: {mdp_path}")
    df = mdp_df[mdp_df[col].astype(str) == trade_date]
    if df.empty:
        raise ReferenceAssetUnavailable(
            f"MDP stock_st asset has no rows for trade_date={trade_date}: {mdp_path}"
        )
    output_path = data_dir / "stock_st" / f"stock_st_{trade_date}.csv"
    _ensure_parent_dir(output_path)
    df.to_csv(output_path, index=False)
    print(
        f"Consumed MDP stock_st asset ({mdp_path}) for trade_date={trade_date} "
        f"-> {output_path} ({len(df)} rows)"
    )
    return FetchResult(label="stock_st", path=output_path, rows=len(df))


def backfill_stock_st(
    pro,
    start: date,
    end: date,
    *,
    data_dir: Path,
) -> list[FetchResult]:
    """Backfill compatibility CSVs from the published MDP asset."""
    frame, source = load_mdp_asset("stock_st")
    if "trade_date" not in frame.columns:
        raise ReferenceAssetUnavailable(f"MDP stock_st asset lacks 'trade_date': {source}")
    trade_keys = frame["trade_date"].astype(str).str.replace("-", "", regex=False)
    start_key = start.strftime("%Y%m%d")
    end_key = end.strftime("%Y%m%d")
    trade_dates = sorted(trade_keys[(trade_keys >= start_key) & (trade_keys <= end_key)].unique())
    results: list[FetchResult] = []
    total = len(trade_dates)

    for idx, trade_date in enumerate(trade_dates, start=1):
        output_path = data_dir / "stock_st" / f"stock_st_{trade_date}.csv"

        if has_data_rows(output_path):
            print(f"[{idx}/{total}] {trade_date} 跳过（已存在）")
            continue
        if output_path.exists():
            print(f"[{idx}/{total}] {trade_date} 发现空/无数据文件，重拉")
        else:
            print(f"[{idx}/{total}] {trade_date} 从 MDP 资产导出")

        day_frame = frame[trade_keys == trade_date]
        _ensure_parent_dir(output_path)
        day_frame.to_csv(output_path, index=False)
        results.append(FetchResult(label="stock_st", path=output_path, rows=len(day_frame)))

    return results


def check_zero_row_files(data_dir: Path) -> list[Path]:
    """List stock_st CSV files that have a header but zero data rows."""
    stock_dir = data_dir / "stock_st"
    if not stock_dir.exists():
        raise SystemExit(f"目录不存在：{stock_dir}")

    candidates = sorted(stock_dir.glob("stock_st_*.csv"))
    dated: list[tuple[Path, date]] = []
    for path in candidates:
        parsed = _extract_trade_date_from_path(path)
        if parsed:
            dated.append((path, parsed))

    if not dated:
        print("共检查 0 个文件。")
        return []

    frame, source = load_mdp_asset("stock_st")
    if "trade_date" not in frame.columns:
        raise ReferenceAssetUnavailable(f"MDP stock_st asset lacks 'trade_date': {source}")
    trading_set = set(frame["trade_date"].astype(str).str.replace("-", "", regex=False))

    zero_rows: list[Path] = []
    for path, dt in dated:
        if dt.strftime("%Y%m%d") not in trading_set:
            continue
        try:
            if not has_data_rows(path):
                zero_rows.append(path)
        except Exception as exc:
            print(f"读取 {path} 失败：{exc}")

    if zero_rows:
        print(f"发现 {len(zero_rows)} 个零行文件：")
        for p in zero_rows:
            print(f"  - {p.relative_to(data_dir)}")
    else:
        print("未发现零行文件。")

    return zero_rows
