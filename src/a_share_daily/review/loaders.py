"""Data loaders for the A-share evening review fact layer."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .. import data as D
from ..market_temperature import build_market_temperature

DEFAULT_EVENING_ARCHIVE_DIR = D.PROJECT_ROOT / "out" / "a_share_daily" / "history"


def _is_stock(code: str) -> bool:
    """True for individual stocks (not indices, not concepts)."""
    if code.endswith(".SH") and code[:6] in {
        "000001",
        "000002",
        "000003",
        "000004",
        "000005",
        "000006",
        "000007",
        "000008",
        "000009",
        "000010",
        "000011",
        "000012",
        "000013",
        "000014",
        "000015",
        "000016",
        "000017",
        "000018",
        "000019",
        "000020",
        "000300",
        "000688",
        "000852",
        "000905",
    }:
        return False
    if code.endswith(".SZ") and code[:6] in {
        "399001",
        "399005",
        "399006",
        "399016",
        "399102",
        "399106",
        "399300",
        "399303",
        "399852",
        "399905",
    }:
        return False
    return not code.endswith(".TI")


def load_index_overview(trade_date: str) -> dict[str, Any]:
    """Index-level market snapshot."""
    try:
        idx = D.read_index_daily()
        idx = idx[idx["trade_date"] == trade_date]
    except Exception:
        return {}

    indices = {}
    for code, name in D.TRACKED_INDICES.items():
        row = idx[idx["ts_code"] == code]
        if row.empty:
            continue
        r = row.iloc[0]
        indices[code] = {
            "name": name,
            "close": float(r["close"]),
            "pct_chg": float(r["pct_chg"]),
            "amount": float(r["amount"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "pre_close": float(r["pre_close"]),
        }
    return indices


def load_market_overview(trade_date: str) -> dict[str, Any]:
    """Market aggregates from individual stocks."""
    daily = D.read_daily(trade_date)
    stocks = daily[daily["ts_code"].apply(_is_stock)].copy()

    stocks["pct_chg"] = pd.to_numeric(stocks["pct_chg"], errors="coerce")
    stocks["amount"] = pd.to_numeric(stocks["amount"], errors="coerce")

    up = int((stocks["pct_chg"] > 0).sum())
    down = int((stocks["pct_chg"] < 0).sum())
    flat = int((stocks["pct_chg"] == 0).sum())
    total = len(stocks)

    total_amount = float(stocks["amount"].sum())
    median_pct = float(stocks["pct_chg"].median())
    avg_pct = float(stocks["pct_chg"].mean())
    wavg_pct = (
        float((stocks["pct_chg"] * stocks["amount"]).sum() / stocks["amount"].sum())
        if total_amount > 0
        else 0.0
    )

    # Distribution
    bins = [
        (-100, -9.9),
        (-9.9, -7),
        (-7, -5),
        (-5, -3),
        (-3, -1),
        (-1, 0),
        (0, 1),
        (1, 3),
        (3, 5),
        (5, 7),
        (7, 9.9),
        (9.9, 100),
    ]
    dist = {}
    for lo, hi in bins:
        cnt = int(((stocks["pct_chg"] >= lo) & (stocks["pct_chg"] < hi)).sum())
        if cnt > 0:
            dist[f"{lo}~{hi}%"] = cnt

    # Top movers (exclude IPOs)
    stocks_clean = stocks[stocks["pct_chg"].between(-30, 30)]
    top_up = stocks_clean.nlargest(5, "pct_chg")[["ts_code", "pct_chg", "close"]].to_dict("records")
    top_down = stocks_clean.nsmallest(5, "pct_chg")[["ts_code", "pct_chg", "close"]].to_dict(
        "records"
    )

    # VWAP
    vwap_ratio = D.vwap_above_ratio(stocks)
    intra = D.intraday_structure(stocks)

    # Prefer exchange-provided limit prices.  The pct-change fallback is kept
    # explicit because board and ST rules cannot be inferred safely from the
    # stock code alone.
    limit_method = "pct_chg_approx"
    limit_up_count: int | None = None
    limit_count_error = ""
    try:
        limit_status = D.read_limit_status(trade_date)
        limit_up_count, dl_count = D.get_exact_limit_counts(stocks, limit_status)
        limit_method = "exchange_limit_price"
    except Exception as exc:
        limit_count_error = f"{type(exc).__name__}: {exc}"
        dl_count = D.get_down_limit_count(stocks)
    up5 = D.get_up5_count(stocks)
    down5 = D.get_down5_count(stocks)

    return {
        "median_pct_chg": median_pct,
        "mean_pct_chg": avg_pct,
        "wavg_pct_chg": wavg_pct,
        "breadth": {
            "up": up,
            "down": down,
            "flat": flat,
            "total": total,
            "up_ratio": round(up / total * 100, 1) if total else 0,
        },
        "turnover_total": total_amount,
        "distribution": dist,
        "top_gainers": top_up,
        "top_losers": top_down,
        "vwap_above_ratio": vwap_ratio,
        "intraday": intra,
        "limit_up_count": limit_up_count,
        "down_limit_count": dl_count,
        "limit_count_method": limit_method,
        "limit_count_error": limit_count_error,
        # Compatibility alias for older consumers.  Check limit_count_method
        # before describing this value as approximate.
        "down_limit_approx": dl_count,
        "up5_count": up5,
        "down5_count": down5,
    }


def load_limit_analysis(
    trade_date: str,
    *,
    overview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Limit-up/down statistics."""
    overview = overview or load_market_overview(trade_date)
    exact_up = overview.get("limit_up_count")
    down_count = int(overview.get("down_limit_count", overview.get("down_limit_approx", 0)) or 0)
    method = str(overview.get("limit_count_method") or "pct_chg_approx")
    up = pd.DataFrame()
    source_error = ""
    try:
        df = D.read_limit_list(trade_date)
    except Exception:
        source_error = "limit_list_ths not available"
    else:
        up = (
            df[df["limit_type"].str.contains("涨停", na=False)]
            if "limit_type" in df.columns
            else df
        )
    status_counts = (
        up["status"].value_counts().to_dict() if not up.empty and "status" in up.columns else {}
    )

    # Max 连板 from limit_step
    max_board = 0
    try:
        step = D.read_limit_step(trade_date)
        if not step.empty:
            max_board = int(step["nums"].max()) if "nums" in step.columns else 0
    except Exception:
        pass

    count = int(exact_up) if exact_up is not None else None if source_error else int(len(up))
    result = {
        "limit_up": {"count": count, "method": method if exact_up is not None else "limit_pool"},
        "limit_down": {"count": down_count, "method": method},
        "limit_up_names": up["name"].tolist()[:15] if not up.empty else [],
        "status_breakdown": status_counts,
        "limit_down_note": (
            "按交易所当日跌停价精确计算"
            if method == "exchange_limit_price"
            else "缺少当日涨跌停价，按 pct_chg 近似计算"
        ),
        "max_board": max_board,
    }
    if source_error:
        result["error"] = source_error
    return result


def load_moneyflow(trade_date: str) -> dict[str, Any]:
    """Northbound + sector money flow."""
    result: dict[str, Any] = {}

    # Northbound (万元)
    try:
        hsgt = D.read_moneyflow_hsgt(trade_date)
        if not hsgt.empty:
            r = hsgt.iloc[0]
            result["northbound"] = {
                "north_net": float(r.get("north_money", 0)) * 1e4,
                "south_net": float(r.get("south_money", 0)) * 1e4,
                "hgt": float(r.get("hgt", 0)) * 1e4,
                "sgt": float(r.get("sgt", 0)) * 1e4,
            }
    except Exception:
        pass

    # HSGT top 10 active
    try:
        top10 = D.read_hsgt_top10(trade_date)
        if not top10.empty:
            top10["change_n"] = pd.to_numeric(top10["change"], errors="coerce")
            buy = top10.nlargest(5, "change_n")[["name", "change_n", "market_type"]].to_dict(
                "records"
            )
            result["north_active_buy"] = [{"name": r["name"], "change": r["change_n"]} for r in buy]
    except Exception:
        pass

    # Moneyflow THS (万元 → 元)
    try:
        mf = D.read_moneyflow_ths(trade_date)
        if not mf.empty:
            mf["net_amount"] = pd.to_numeric(mf["net_amount"], errors="coerce")
            net_in = float(mf[mf["net_amount"] > 0]["net_amount"].sum()) * 1e4
            net_out = float(mf[mf["net_amount"] < 0]["net_amount"].sum()) * 1e4
            result["moneyflow"] = {
                "net_in": net_in,
                "net_out": net_out,
                "net_total": net_in + net_out,
                "inflow_stocks": int((mf["net_amount"] > 0).sum()),
                "outflow_stocks": int((mf["net_amount"] < 0).sum()),
            }
    except Exception:
        pass

    return result


def load_margin(trade_date: str) -> dict[str, Any]:
    """Margin trading (元)."""
    try:
        df = D.read_margin(trade_date)
        if df.empty:
            return {}
        total_rz = float(df["rzye"].sum())
        total_rq = float(df["rqye"].sum())
        return {
            "margin_balance": total_rz + total_rq,
            "financing_balance": total_rz,
            "short_balance": total_rq,
        }
    except Exception:
        return {}


def load_hot_sectors(trade_date: str) -> dict[str, Any]:
    """Hot concept sectors."""
    try:
        df = D.read_dc_concept(trade_date)
        if df.empty:
            return {}
        for col in [
            "pct_change",
            "lead_stock_pct_change",
            "z_t_num",
            "main_change",
            "hot",
        ]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        top_change = df.nlargest(10, "pct_change")[
            ["name", "pct_change", "lead_stock", "lead_stock_pct_change", "z_t_num"]
        ].to_dict("records")
        top_fund_in = (
            df.nlargest(5, "main_change")[["name", "main_change", "lead_stock"]].to_dict("records")
            if "main_change" in df.columns
            else []
        )
        return {
            "top_by_change": top_change,
            "top_by_fund": top_fund_in,
            "total_concepts": int(len(df)),
        }
    except Exception:
        return {}


def load_industry_stats(trade_date: str) -> pd.DataFrame:
    """Per-industry stats from daily + ths_member."""
    try:
        daily = D.read_daily(trade_date)
        stocks = daily[daily["ts_code"].apply(_is_stock)].copy()
        stocks["pct_chg"] = pd.to_numeric(stocks["pct_chg"], errors="coerce")
        return D.get_industry_stats(stocks)
    except Exception:
        return pd.DataFrame()


def load_top_amount_stocks(trade_date: str, n: int = 20) -> pd.DataFrame:
    """Top N stocks by turnover amount."""
    daily = D.read_daily(trade_date)
    stocks = daily[daily["ts_code"].apply(_is_stock)].copy()
    stocks["amount"] = pd.to_numeric(stocks["amount"], errors="coerce")
    stocks["pct_chg"] = pd.to_numeric(stocks["pct_chg"], errors="coerce")
    top = stocks.nlargest(n, "amount")[["ts_code", "amount", "pct_chg", "close"]]
    top["amount_yi"] = top["amount"] / 1e5  # 千元→亿
    return top


def load_turnover_history(trade_date: str, lookback: int = 20) -> list[dict[str, Any]]:
    """Load prior market turnover snapshots for a rolling relative baseline."""
    dataset_dir = D.DATA_ROOT / "daily"
    latest_dirs = sorted(dataset_dir.glob("*_latest"))
    if not latest_dirs:
        return []
    latest_dir = next(
        (path for path in latest_dirs if path.name == "a_share_all_daily_latest"),
        latest_dirs[-1],
    )
    partitions = sorted(
        path.name.removeprefix("trade_date=")
        for path in (latest_dir / "data").glob("trade_date=*")
        if path.name.removeprefix("trade_date=") < trade_date
    )[-lookback:]
    history: list[dict[str, Any]] = []
    for day in partitions:
        try:
            daily = pd.read_parquet(latest_dir / "data" / f"trade_date={day}" / "part.parquet")
            stocks = daily[daily["ts_code"].astype(str).map(_is_stock)].copy()
            amount = pd.to_numeric(stocks["amount"], errors="coerce").sum()
        except Exception:
            continue
        history.append({"trade_date": day, "turnover_total": float(amount)})
    return history


def load_previous_market_temperature(trade_date: str) -> dict[str, Any] | None:
    """Read the latest archived temperature payload before ``trade_date``."""
    archive_dir = Path(
        os.environ.get("A_SHARE_EVENING_ARCHIVE_DIR", str(DEFAULT_EVENING_ARCHIVE_DIR))
    ).expanduser()
    candidates: list[tuple[str, Path]] = []
    for path in archive_dir.glob("evening_review_*.json"):
        archived_date = path.stem.removeprefix("evening_review_")
        if len(archived_date) == 8 and archived_date.isdigit() and archived_date < trade_date:
            candidates.append((archived_date, path))
    for _date, path in sorted(candidates, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        temperature = payload.get("market_temperature") if isinstance(payload, dict) else None
        if isinstance(temperature, dict):
            return temperature
    return None


def build_review_payload(trade_date: str) -> dict[str, Any]:
    """Build the structured fact layer plus the deterministic interpretation layer."""
    indices = load_index_overview(trade_date)
    overview = load_market_overview(trade_date)
    limits = load_limit_analysis(trade_date, overview=overview)
    moneyflow = load_moneyflow(trade_date)
    industry = load_industry_stats(trade_date)
    industry_records = industry.to_dict("records") if not industry.empty else []
    turnover_history = load_turnover_history(trade_date)
    market_temperature = build_market_temperature(
        trade_date,
        overview=overview,
        indices=indices,
        limits=limits,
        moneyflow=moneyflow,
        industries=industry_records,
        turnover_history=turnover_history,
        previous=load_previous_market_temperature(trade_date),
    )
    top_amount = load_top_amount_stocks(trade_date).to_dict("records")
    return {
        "trade_date": trade_date,
        "generated_at": datetime.now().isoformat(),
        "market_temperature": market_temperature,
        "indices": indices,
        "overview": overview,
        "limits": limits,
        "moneyflow": moneyflow,
        "margin": load_margin(trade_date),
        "hot_sectors": load_hot_sectors(trade_date),
        "industry_stats": industry_records,
        "top_amount_stocks": top_amount,
        "turnover_history": turnover_history,
    }
