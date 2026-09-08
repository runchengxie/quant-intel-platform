"""Trade calendar helpers for non-trading-day alignment."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .retry import FetchRunner, RateLimiter


def load_trade_dates(pro, start: date, end: date, *, exchange: str = "SSE") -> list[date]:
    """Return sorted list of trading days in [start, end] for the given exchange."""
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    runner = FetchRunner(RateLimiter(min_interval=0.35))
    cal = runner.call(
        f"trade_cal {exchange} {start_str}->{end_str}",
        lambda: pro.trade_cal(exchange=exchange, start_date=start_str, end_date=end_str),
    )
    if cal is None or cal.empty:
        return []
    trading_days = cal[cal["is_open"] == 1]["cal_date"]
    return sorted(datetime.strptime(str(d), "%Y%m%d").date() for d in trading_days)


def latest_trading_date(
    pro, target: date, *, lookback_days: int = 30, exchange: str = "SSE"
) -> date:
    """Return the latest trading date <= target.

    Raises SystemExit if none found within *lookback_days*.
    """
    start = target - timedelta(days=lookback_days)
    dates = load_trade_dates(pro, start, target, exchange=exchange)
    if not dates:
        raise SystemExit(f"未能在最近 {lookback_days} 天内找到交易日，检查交易所日历或日期设置。")
    return max(dates)


def normalize_trade_date(pro, trade_date: str, *, exchange: str = "SSE") -> tuple[str, bool]:
    """Ensure *trade_date* falls on a trading day. Returns (final_YMD, was_adjusted)."""
    target = datetime.strptime(trade_date, "%Y%m%d").date()
    last_open = latest_trading_date(pro, target, exchange=exchange)
    adjusted = last_open != target
    return last_open.strftime("%Y%m%d"), adjusted
