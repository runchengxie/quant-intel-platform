"""Comparable financing observations with an explicit exchange scope."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TypedDict

import pandas as pd

EXCHANGES = frozenset({"SSE", "SZSE", "BSE"})


class MarginHistoryRow(TypedDict):
    date: str
    rzye: float
    exchange_scope: str


def comparable_margin_rows(frames: Mapping[str, pd.DataFrame]) -> list[MarginHistoryRow]:
    """Use only exchanges available in every plotted observation."""
    observed = {day: frame for day, frame in frames.items() if not frame.empty}
    scopes = []
    for frame in observed.values():
        codes = frame["exchange_id"]
        if codes.isna().any() or codes.duplicated().any():
            raise ValueError("missing or duplicate margin exchange rows")
        scope = set(codes)
        if not scope <= EXCHANGES:
            raise ValueError("unknown margin exchange")
        values = pd.to_numeric(frame["rzye"], errors="raise")
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError("invalid financing balance")
        scopes.append(scope)
    common = set.intersection(*scopes) if scopes else set()
    if not common:
        return []
    return [
        {
            "date": day,
            "rzye": float(pd.to_numeric(frame.loc[frame["exchange_id"].isin(common), "rzye"]).sum())
            / 1e8,
            "exchange_scope": "/".join(sorted(common)),
        }
        for day, frame in sorted(observed.items())
    ]


def margin_source_label(label: str, scope: object) -> str:
    """Legacy unscoped points remain explicitly unverified, not full-market totals."""
    text = str(scope or "")
    exchanges = set(text.split("/"))
    status = "全市场" if exchanges == EXCHANGES else "部分交易所"
    return f"{label}（{status}，覆盖 {text or '未核实'}）"
