"""Data lake readers for A-share daily report.

All paths resolve under DATA_PLATFORM_ROOT/assets/tushare/a_share/.
Supports both partitioned (trade_date=YYYYMMDD/) and flat parquet layouts.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from market_intel_config import data_platform_root

DATA_ROOT = data_platform_root() / "assets" / "tushare" / "a_share"

# ── Config ───────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _data_root() -> Path:
    return data_platform_root(required=True) / "assets" / "tushare" / "a_share"


def _resolve_cjk_font(*candidates: str) -> str:
    """Return the first available CJK font path across platforms."""
    for path in candidates:
        if Path(path).exists():
            return path
    return candidates[-1]  # fallback to last candidate


_CJK_FONT = _resolve_cjk_font(
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
)

# Key indices we track
TRACKED_INDICES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
}


def _latest_date(dataset: str, as_of_date: str | None = None) -> str | None:
    """Find the latest partition, optionally bounded by a report date."""
    p = _data_root() / dataset
    if not p.exists():
        return None
    latest_dirs = list(p.glob("*_latest/data/trade_date=*"))
    if not latest_dirs:
        return None
    dates = sorted(d.name.split("=")[1] for d in latest_dirs)
    if as_of_date:
        dates = [value for value in dates if value <= as_of_date]
    return dates[-1] if dates else None


def _read_partitioned(dataset: str, trade_date: str) -> pd.DataFrame:
    """Read a trade_date-partitioned parquet dataset."""
    latest_dirs = list((_data_root() / dataset).glob("*_latest"))
    if not latest_dirs:
        raise FileNotFoundError(f"dataset latest link missing: {dataset}")
    latest_dir = latest_dirs[0]
    p = latest_dir / "data" / f"trade_date={trade_date}" / "part.parquet"
    return pd.read_parquet(p)


def _read_flat(dataset: str) -> pd.DataFrame:
    """Read a flat (non-partitioned) parquet dataset."""
    latest_dir = list((_data_root() / dataset).glob("*_latest"))[0]
    p = latest_dir / "data" / "part.parquet"
    return pd.read_parquet(p)


# ── Public readers ───────────────────────────────────────────


def read_daily(trade_date: str) -> pd.DataFrame:
    """Individual stock daily OHLCV."""
    return _read_partitioned("daily", trade_date)


def read_index_daily() -> pd.DataFrame:
    """Index daily OHLCV (flat, all dates in one file)."""
    return _read_flat("index_daily")


def read_limit_list(trade_date: str) -> pd.DataFrame:
    """Limit-up list (涨停池)."""
    return _read_partitioned("limit_list_ths", trade_date)


def read_limit_step(trade_date: str) -> pd.DataFrame:
    """连板统计."""
    return _read_partitioned("limit_step", trade_date)


def read_limit_status(trade_date: str) -> pd.DataFrame:
    """Daily exchange limit prices for exact limit-up/down classification."""
    return _read_partitioned("limit_status", trade_date)


def read_moneyflow_ths(trade_date: str) -> pd.DataFrame:
    """THS moneyflow (万元)."""
    return _read_partitioned("moneyflow_ths", trade_date)


def read_moneyflow_hsgt(trade_date: str) -> pd.DataFrame:
    """Northbound moneyflow (万元)."""
    return _read_partitioned("moneyflow_hsgt", trade_date)


def read_hsgt_top10(trade_date: str) -> pd.DataFrame:
    """Northbound top 10 active stocks."""
    return _read_partitioned("hsgt_top10", trade_date)


def read_margin(trade_date: str) -> pd.DataFrame:
    """Margin trading balance (元)."""
    return _read_partitioned("margin", trade_date)


def read_dc_concept(trade_date: str) -> pd.DataFrame:
    """东财概念板块."""
    return _read_partitioned("dc_concept", trade_date)


def read_dc_concept_cons(trade_date: str) -> pd.DataFrame:
    """东方财富概念成分股."""
    return _read_partitioned("dc_concept_cons", trade_date)


def read_ths_member() -> pd.DataFrame:
    """同花顺行业→个股映射 (flat)."""
    return _read_flat("ths_member")


# ── Derived data ─────────────────────────────────────────────


def stock_industry_map() -> dict[str, str]:
    """Build ts_code → SW industry_name mapping from index_member data.

    Uses sw_industry_member (申万一级行业成分股) saved to data lake.
    """
    try:
        member = _read_flat("sw_industry_member")
        return dict(zip(member["con_code"], member["industry_name"], strict=False))
    except Exception:
        return {}


def get_industry_stats(daily: pd.DataFrame) -> pd.DataFrame:
    """Compute per-industry stats: avg pct_chg, up_ratio, limit counts."""
    ind_map = stock_industry_map()
    df = daily.copy()
    df["industry"] = [ind_map.get(str(code), "其他") for code in df["ts_code"]]

    stats = (
        df.groupby("industry")
        .agg(
            avg_pct_chg=("pct_chg", "mean"),
            median_pct_chg=("pct_chg", "median"),
            stock_count=("ts_code", "count"),
            up_count=("pct_chg", lambda x: int((x > 0).sum())),
            down_count=("pct_chg", lambda x: int((x < 0).sum())),
        )
        .reset_index()
    )
    stats["up_ratio"] = (stats["up_count"] / stats["stock_count"] * 100).round(1)

    return stats.sort_values("avg_pct_chg", ascending=False)


def get_down_limit_count(daily: pd.DataFrame) -> int:
    """Approximate 跌停 count from pct_chg.

    主板/中小板: ≈ -10%, 创业板/科创板: ≈ -20%.
    """
    df = daily.copy()

    def _is_down_limit(ts_code: str, pct: float) -> bool:
        if ts_code.startswith("300") or ts_code.startswith("301") or ts_code.startswith("688"):
            return pct <= -19.5
        return pct <= -9.5

    return int(
        sum(
            _is_down_limit(str(ts_code), float(pct))
            for ts_code, pct in zip(df["ts_code"], df["pct_chg"], strict=False)
        )
    )


def get_exact_limit_counts(
    daily: pd.DataFrame,
    limit_status: pd.DataFrame,
) -> tuple[int, int]:
    """Return exact (limit_up, limit_down) counts from exchange limit prices.

    The limit-status dataset already incorporates board, ST and listing-specific
    price-limit rules.  Comparing the close with those prices avoids treating
    Beijing Exchange moves or near-limit closes as sealed limit events.
    """
    required_daily = {"ts_code", "close"}
    required_limits = {"ts_code", "up_limit", "down_limit"}
    if not required_daily.issubset(daily.columns) or not required_limits.issubset(
        limit_status.columns
    ):
        missing = sorted(
            (required_daily - set(daily.columns)) | (required_limits - set(limit_status.columns))
        )
        raise ValueError(f"limit count inputs missing columns: {', '.join(missing)}")

    prices = daily[["ts_code", "close"]].copy()
    limits = limit_status[["ts_code", "up_limit", "down_limit"]].copy()
    merged = prices.merge(limits, on="ts_code", how="inner", validate="one_to_one")
    coverage = len(merged) / len(prices) if len(prices) else 0.0
    if coverage < 0.98:
        raise ValueError(f"limit-status coverage too low for exact counts: {coverage:.1%}")
    for column in ("close", "up_limit", "down_limit"):
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    valid = merged.dropna(subset=["close", "up_limit", "down_limit"])
    valid = valid[(valid["up_limit"] > 0) & (valid["down_limit"] > 0)]
    valid_coverage = len(valid) / len(prices) if len(prices) else 0.0
    if valid_coverage < 0.98:
        raise ValueError(
            f"valid limit-status coverage too low for exact counts: {valid_coverage:.1%}"
        )
    tolerance = 1e-6
    limit_up = int((valid["close"] >= valid["up_limit"] - tolerance).sum())
    limit_down = int((valid["close"] <= valid["down_limit"] + tolerance).sum())
    return limit_up, limit_down


def get_up5_count(daily: pd.DataFrame) -> int:
    """Count stocks with pct_chg >= 5%."""
    return int((daily["pct_chg"] >= 5).sum())


def get_down5_count(daily: pd.DataFrame) -> int:
    """Count stocks with pct_chg <= -5%."""
    return int((daily["pct_chg"] <= -5).sum())


def compute_vwap(daily: pd.DataFrame) -> pd.Series:
    """Approximate VWAP = amount * 10 / vol.

    Tushare units: amount in 千元, vol in 手 (100 shares).
    VWAP = amount(千元) * 1000 / (vol(手) * 100) = amount * 10 / vol
    """
    return daily["amount"] * 10 / daily["vol"].replace(0, pd.NA)


def vwap_above_ratio(daily: pd.DataFrame) -> float:
    """Ratio of stocks closing above approximate VWAP."""
    vwap = compute_vwap(daily)
    above = (daily["close"] >= vwap).sum()
    return round(above / len(daily) * 100, 1)


def intraday_structure(daily: pd.DataFrame) -> dict:
    """Intraday structure from OHLC:
    - gap_open: (open - pre_close) / pre_close
    - day_range: (high - low) / pre_close
    - close_position: (close - low) / (high - low)  -- where close sits in day's range
    """
    o, h, lo, c, pc = (
        daily["open"],
        daily["high"],
        daily["low"],
        daily["close"],
        daily["pre_close"],
    )

    gap = ((o - pc) / pc * 100).median()
    day_range = ((h - lo) / pc * 100).median()
    hl_range = h - lo
    close_pos = ((c - lo) / hl_range.replace(0, pd.NA) * 100).median()

    return {
        "gap_open_pct": round(float(gap), 2),
        "median_day_range_pct": round(float(day_range), 2),
        "median_close_position_pct": round(float(close_pos), 1),
    }


def get_week_dates(trade_date: str) -> list[str]:
    """Return the five preceding weekdays ending at ``trade_date``."""
    ref = date(int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:]))
    candidates = [
        ref - timedelta(days=i) for i in range(7) if (ref - timedelta(days=i)).weekday() < 5
    ]
    return [item.strftime("%Y%m%d") for item in reversed(candidates[:5])]


def cjk_font_available() -> bool:
    return Path(_CJK_FONT).exists()


def cjk_font_path() -> str:
    return _CJK_FONT
