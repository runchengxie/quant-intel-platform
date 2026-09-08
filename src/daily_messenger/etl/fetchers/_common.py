"""ETL 抓取层共享的纯工具函数与常量。

这些符号不绑定具体数据源，被多个 fetchers 子模块和 run_fetch 复用。放到
独立模块后，各数据源模块从本模块导入，避免 fetchers 子模块反向依赖
run_fetch 造成循环导入。
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from daily_messenger.etl.config import env_truthy as _env_truthy

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _yahoo_allowed() -> bool:
    if os.getenv("DISABLE_YAHOO", "0") == "1":
        return False
    return _env_truthy(os.getenv("YFINANCE_FALLBACK"))


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_number(value: str) -> float | None:
    text = value.strip()
    if not text or text == "-":
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("() ")
    normalized = text.replace(",", "").replace("\u2212", "-")
    try:
        number = float(normalized)
    except ValueError:
        return None
    return -number if negative else number


def _latest_date(rows: Iterable[list[str]]) -> list[str] | None:
    parsed: list[tuple[datetime, list[str]]] = []
    for row in rows:
        if not row:
            continue
        first = row[0].strip()
        try:
            parsed_date = datetime.strptime(first, "%d %b %Y")
        except ValueError:
            continue
        parsed.append((parsed_date, row))
    if not parsed:
        return None
    parsed.sort(key=lambda item: item[0], reverse=True)
    return parsed[0][1]
