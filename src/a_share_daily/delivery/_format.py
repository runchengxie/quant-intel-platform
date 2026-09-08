"""交付层的纯格式化与 IO 工具。

这些函数无副作用、不依赖任何业务常量，被 report_delivery 的渲染与
投递逻辑复用。单独成模块后，report_delivery 通过 re-export 保持兼容。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


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


def _fmt_yuan(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    abs_number = abs(number)
    sign = "-" if number < 0 else ""
    if abs_number >= 1e12:
        return f"{sign}{abs_number / 1e12:.2f}万亿"
    if abs_number >= 1e8:
        return f"{sign}{abs_number / 1e8:.2f}亿"
    if abs_number >= 1e4:
        return f"{sign}{abs_number / 1e4:.2f}万"
    return f"{number:.0f}"


def _date_dash(trade_date: str) -> str:
    if len(trade_date) == 8 and trade_date.isdigit():
        return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    return trade_date


def _dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list) else []
