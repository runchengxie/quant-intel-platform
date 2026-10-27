"""Shared formatting and file helpers for report rendering and delivery."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from a_share_daily.report_messages import message


def _read_text(path: str | Path) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8").strip()


def _load_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_text(path: str | Path, text: str) -> Path:
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text.rstrip() + "\n", encoding="utf-8")
    return resolved


def _fmt_pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:+.2f}%"


def _fmt_close(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    return f"{number:.2f}"


def _fmt_yuan(value: Any, *, locale: str = "zh-CN") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    abs_number = abs(number)
    sign = "-" if number < 0 else ""
    if abs_number >= 1e12:
        return message(locale, "currency.trillion", value=f"{sign}{abs_number / 1e12:.2f}")
    if abs_number >= 1e8:
        return message(locale, "currency.hundred_million", value=f"{sign}{abs_number / 1e8:.2f}")
    if abs_number >= 1e4:
        return message(locale, "currency.ten_thousand", value=f"{sign}{abs_number / 1e4:.2f}")
    return message(locale, "currency.yuan", value=f"{number:.0f}")


def _date_dash(trade_date: str) -> str:
    if len(trade_date) == 8 and trade_date.isdigit():
        return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    return trade_date


def _dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list) else []
