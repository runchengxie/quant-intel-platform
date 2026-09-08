"""Shared ETL data transfer types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FetchStatus:
    name: str
    ok: bool
    message: str = ""


@dataclass
class QuoteSnapshot:
    day: str
    close: float
    change_pct: float
    source: str
