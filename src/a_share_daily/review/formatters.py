"""Formatting helpers for the A-share evening review renderers."""

from __future__ import annotations


def _fmt_yuan(n: float) -> str:
    if abs(n) >= 1e12:
        return f"{n / 1e12:.2f}万亿"
    if abs(n) >= 1e8:
        return f"{n / 1e8:.2f}亿"
    if abs(n) >= 1e4:
        return f"{n / 1e4:.2f}万"
    return f"{n:.0f}"


def _pct(v: float) -> str:
    if v > 0:
        return f"+{v:.2f}%"
    return f"{v:.2f}%"


def _sign(n: float) -> str:
    if n > 0:
        return f"+{_fmt_yuan(n)}"
    return f"-{_fmt_yuan(abs(n))}"
