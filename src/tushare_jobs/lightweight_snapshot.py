"""Lightweight TuShare daily snapshot for offshore GH Actions runner.

Fetches a focused set of daily data and prints JSON to stdout.
Designed for backup agent consumption — no data lake dependency.

Token priority:
  TUSHARE_TOKEN_2 + TUSHARE_API_URL_2  → proxy account (15000 pts, tries first)
  TUSHARE_TOKEN                         → main account (fallback)

The proxy token covers basic APIs plus limit_list_d; if unavailable the
script degrades gracefully.  All failures are captured in ``errors`` — the
script always prints valid JSON.

Usage:
    TUSHARE_TOKEN=xxx uv run python -m tushare_jobs.lightweight_snapshot [YYYYMMDD]
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .client import create_tushare_client, resolve_tushare_credentials

BJT = ZoneInfo("Asia/Shanghai")

DEFAULT_INDICES = [
    ("000001.SH", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("399006.SZ", "创业板指"),
    ("000016.SH", "上证50"),
    ("000300.SH", "沪深300"),
    ("000905.SH", "中证500"),
    ("000852.SH", "中证1000"),
    ("399673.SZ", "创业板50"),
]


def _init_pro(
    *,
    env: Mapping[str, str] | None = None,
    tushare_module: Any | None = None,
) -> tuple[Any, str | None]:
    """Initialise TuShare client.

    Tries TUSHARE_TOKEN_2 with proxy URL first (higher permissions),
    then falls back to TUSHARE_TOKEN with default API.

    Returns (pro_api, source_label).
    """
    if tushare_module is None:
        import tushare as tushare_module

    failed_envs: list[str] = []
    for credential in resolve_tushare_credentials(env=env):
        try:
            pro = create_tushare_client(credential, tushare_module=tushare_module)
            test = pro.trade_cal(exchange="SSE", start_date="20260626", end_date="20260626")
            if not test.empty:
                label = credential.label
                if credential.token_env == "TUSHARE_TOKEN_2" and credential.api_url:
                    label = f"proxy ({credential.api_url})"
                return pro, label
        except Exception:  # noqa: BLE001 - retry without exposing provider errors or tokens
            pass
        failed_envs.append(credential.token_env)

    raise SystemExit(
        "No configured TuShare credential passed the connectivity check: " + ", ".join(failed_envs)
    )


def _resolve_trade_date(pro: Any, override: str | None) -> str:
    """Return the most recent trading day with available data."""
    candidate = override or datetime.now(tz=BJT).strftime("%Y%m%d")

    df = pro.trade_cal(exchange="SSE", start_date="20240101", end_date=candidate, is_open="1")
    if df.empty:
        raise SystemExit(f"No trading day found <= {candidate}")

    trading_days = sorted(df["cal_date"].tolist(), reverse=True)

    for td in trading_days[:3]:
        try:
            test = pro.index_daily(ts_code="000001.SH", trade_date=td)
            if not test.empty:
                return str(td)
        except Exception:
            pass

    return str(trading_days[0])


def fetch_index_daily(pro: Any, trade_date: str) -> dict[str, dict]:
    """Fetch index daily data — one code at a time."""
    result: dict[str, dict] = {}
    for ts_code, name in DEFAULT_INDICES:
        df = pro.index_daily(ts_code=ts_code, trade_date=trade_date)
        if df.empty:
            continue
        row = df.iloc[0]
        result[ts_code] = {
            "name": name,
            "close": float(row["close"]),
            "pct_chg": float(row["pct_chg"]),
            "vol": float(row["vol"]),
            "amount": float(row["amount"]),
        }
    return result


def _try_limit_query(pro: Any, trade_date: str, limit_type: str) -> list[dict] | None:
    """Query limit_list_d for one direction.  Returns None on permission error."""
    try:
        df = pro.limit_list_d(trade_date=trade_date, limit_type=limit_type)
    except Exception as e:
        msg = str(e)
        if "权限" in msg or "permission" in msg.lower() or "token不对" in msg:
            return None
        raise
    if df.empty:
        return []
    entries: list[dict] = []
    for _, row in df.iterrows():
        entries.append(
            {
                "ts_code": str(row["ts_code"]),
                "name": str(row.get("name", "")),
                "pct_chg": float(row.get("pct_chg", 0) or 0),
                "close": float(row.get("close", 0) or 0),
                "limit_times": int(row.get("limit_times", 1) or 1),
                "first_time": str(row.get("first_time", "")),
            }
        )
    return entries


def fetch_limit_list(pro: Any, trade_date: str) -> dict:
    """Fetch limit-up and limit-down stocks.

    Proxy-based tokens require separate U and D calls.
    """
    try:
        up = _try_limit_query(pro, trade_date, "U")
        down = _try_limit_query(pro, trade_date, "D")
    except Exception:
        up = down = None

    if up is not None and down is not None:
        return {"up": up, "down": down, "_unavailable": False}

    return {"_unavailable": True, "_reason": "limit_list_d not available on this token"}


def fetch_moneyflow(pro: Any, trade_date: str) -> dict:
    """Fetch market-wide money flow summary."""
    df = pro.moneyflow(trade_date=trade_date)
    total_buy_elg = 0.0
    total_sell_elg = 0.0
    total_net_amount = 0.0

    entries: list[dict] = []
    for _, row in df.iterrows():
        buy_elg = float(row.get("buy_elg_vol", 0) or 0)
        sell_elg = float(row.get("sell_elg_vol", 0) or 0)
        net_amount = float(row.get("net_mf_amount", 0) or 0)
        total_buy_elg += buy_elg
        total_sell_elg += sell_elg
        total_net_amount += net_amount

        if abs(net_amount) > 1e6 or abs(buy_elg) > 1e6:
            entries.append(
                {
                    "ts_code": str(row["ts_code"]),
                    "name": str(row.get("name", "")),
                    "buy_elg_vol": buy_elg,
                    "sell_elg_vol": sell_elg,
                    "net_mf_amount": net_amount,
                }
            )

    return {
        "total_buy_elg_vol": total_buy_elg,
        "total_sell_elg_vol": total_sell_elg,
        "total_net_mf_amount": total_net_amount,
        "top_entries": sorted(entries, key=lambda x: abs(x["net_mf_amount"]), reverse=True)[:20],
    }


def fetch_market_breadth(pro: Any, trade_date: str) -> dict:
    """Fetch market breadth using the daily endpoint."""
    df = pro.daily(trade_date=trade_date, fields="ts_code,close,pct_chg,vol,amount")
    if df.empty:
        return {
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "total_amount": 0,
            "total_stocks": 0,
        }

    up = df[df["pct_chg"] > 0]
    down = df[df["pct_chg"] < 0]
    flat = df[df["pct_chg"] == 0]
    n = len(df)

    return {
        "up_count": int(len(up)),
        "down_count": int(len(down)),
        "flat_count": int(len(flat)),
        "up_pct": round(len(up) / n * 100, 1) if n else 0,
        "down_pct": round(len(down) / n * 100, 1) if n else 0,
        "total_amount": float(df["amount"].sum()),
        "total_stocks": int(n),
        "avg_pct_chg": round(float(df["pct_chg"].mean()), 2),
        "median_pct_chg": round(float(df["pct_chg"].median()), 2),
    }


def main() -> int:
    trade_date_override = sys.argv[1] if len(sys.argv) > 1 else None
    pro, label = _init_pro()
    trade_date = _resolve_trade_date(pro, trade_date_override)

    snapshot: dict[str, Any] = {
        "trade_date": trade_date,
        "generated_at": datetime.now(tz=BJT).isoformat(),
        "source_label": label,
        "indices": {},
        "limit_list": {},
        "moneyflow": {},
        "breadth": {},
    }

    errors: list[str] = []

    try:
        snapshot["indices"] = fetch_index_daily(pro, trade_date)
    except Exception as e:
        errors.append(f"index_daily: {e}")

    try:
        snapshot["limit_list"] = fetch_limit_list(pro, trade_date)
    except Exception as e:
        errors.append(f"limit_list: {e}")

    try:
        snapshot["moneyflow"] = fetch_moneyflow(pro, trade_date)
    except Exception as e:
        errors.append(f"moneyflow: {e}")

    try:
        snapshot["breadth"] = fetch_market_breadth(pro, trade_date)
    except Exception as e:
        errors.append(f"breadth: {e}")

    snapshot["errors"] = errors

    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
