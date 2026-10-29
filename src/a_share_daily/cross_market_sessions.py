"""Select completed, dated equity sessions for daily and decision-cutoff readers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .global_leadlag import GLOBAL_LEAD_LAG_INSTRUMENTS


def _equity_sessions(symbol: str, trade_date: str) -> tuple[Any, date, date]:
    """Resolve the requested and preceding sessions in the symbol's market."""
    import exchange_calendars as xcals

    from .asia_session import MARKETS, _day

    market = next(
        (item.market for item in GLOBAL_LEAD_LAG_INSTRUMENTS if item.symbol == symbol), "US"
    )
    market = next((key for key, (_, index, _) in MARKETS.items() if index == symbol), market)
    calendar = xcals.get_calendar("XNYS" if market == "US" else MARKETS[market][0])
    target = calendar.date_to_session(_day(trade_date), direction="previous")
    return calendar, target.date(), calendar.previous_session(target).date()


def _equity_quote(data: Any, symbol: str, trade_date: str | None = None) -> dict[str, Any]:
    """Select real session bars; undated compatibility callers retain latest mode."""
    try:
        closes = data["Close"][symbol].dropna()
        if len(closes) < 2:
            return {"error": "insufficient data"}
        if trade_date is None:
            latest, previous = float(closes.iloc[-1]), float(closes.iloc[-2])
            as_of = closes.index[-1].date()
        else:
            calendar, target, preceding = _equity_sessions(symbol, trade_date)
            index = closes.index
            if index.tz is not None:
                index = index.tz_convert(calendar.tz)
            sessions = [value.date() for value in index]
            if len(set(sessions)) != len(sessions):
                return {"error": "duplicate session data"}
            rows = {
                day: value for day, value in zip(sessions, closes, strict=True) if day <= target
            }
            if target not in rows:
                return {"error": "missing target session"}
            if preceding not in rows:
                return {"error": "missing preceding session"}
            latest, previous = float(rows[target]), float(rows[preceding])
            as_of = sessions[sessions.index(target)]
        pct = (latest - previous) / previous * 100 if previous != 0 else 0.0
        return {
            "close": round(latest, 2),
            "pct_chg": round(pct, 2),
            "as_of_date": as_of.isoformat(),
            "source_url": f"https://finance.yahoo.com/quote/{symbol}/history/",
        }
    except Exception:
        return {"error": "no data"}


def _completed_session_date(symbol: str, trade_date: str, decision_at: datetime) -> str:
    calendar, target, _ = _equity_sessions(symbol, trade_date)
    session = calendar.date_to_session(target)
    while calendar.session_close(session).to_pydatetime() > decision_at:
        session = calendar.previous_session(session)
    return session.strftime("%Y%m%d")
