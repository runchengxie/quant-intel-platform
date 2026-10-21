"""Observation-date validation shared by live and snapshot cross-market paths."""

from datetime import date, datetime
from typing import Any


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _quote_date_warnings(data: dict[str, Any], target: date) -> list[str]:
    """Undated, invalid and future observations cannot establish readiness."""
    warnings: list[str] = []
    rows = [
        (symbol, row)
        for section in ("us_stocks", "commodities", "macros")
        for symbol, row in (data.get(section) or {}).items()
        if isinstance(row, dict) and "close" in row
    ]
    cboe = data.get("cboe_putcall")
    if isinstance(cboe, dict) and "vix" in cboe:
        rows.append(("cboe_putcall", cboe))
    for symbol, row in rows:
        observed = _parse_iso_date(row.get("as_of_date"))
        if observed is None:
            warnings.append(f"{symbol}: missing or invalid observation date")
        elif observed > target:
            warnings.append(
                f"{symbol}: future observation date {observed.isoformat()}; "
                f"requested {target.isoformat()}"
            )
    return warnings
