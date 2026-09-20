"""Immutable report content model; presentation is intentionally excluded."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class Metric:
    label: str
    value: str | int | float
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("metric label must be non-empty")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("metric value must be finite")


@dataclass(frozen=True)
class MetricGroup:
    title: str
    metrics: tuple[Metric, ...]


@dataclass(frozen=True)
class PositionCard:
    symbol: str
    name: str
    status: str
    sleeve: str

    def __post_init__(self) -> None:
        if self.status not in {"新增", "保留", "剔除"}:
            raise ValueError("position status must be 新增, 保留, or 剔除")


@dataclass(frozen=True)
class SeriesChart:
    title: str
    points: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if any(not math.isfinite(value) for _, value in self.points):
            raise ValueError("chart values must be finite")


@dataclass(frozen=True)
class Notice:
    text: str
    level: str = "info"


@dataclass(frozen=True)
class ReportSection:
    title: str
    metrics: tuple[MetricGroup, ...] = ()
    positions: tuple[PositionCard, ...] = ()
    charts: tuple[SeriesChart, ...] = ()


@dataclass(frozen=True)
class ReportDocument:
    report_type: str
    report_date: str
    title: str
    metrics: tuple[MetricGroup, ...] = ()
    sections: tuple[ReportSection, ...] = ()
    notices: tuple[Notice, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.report_type.strip() or not self.report_date.strip() or not self.title.strip():
            raise ValueError("report_type, report_date, and title must be non-empty")

    def with_metadata(self, **values: str) -> ReportDocument:
        return replace(self, metadata=tuple(sorted((str(k), str(v)) for k, v in values.items())))

    def content_hash(self) -> str:
        payload: dict[str, Any] = {
            "report_type": self.report_type,
            "report_date": self.report_date,
            "title": self.title,
            "metrics": self.metrics,
            "sections": self.sections,
            "notices": self.notices,
        }
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=lambda x: x.__dict__
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
