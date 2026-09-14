"""Consumer-side validation and display metrics for provider performance artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import Metric, SeriesChart


class PerformanceArtifactError(ValueError):
    """Raised when a performance artifact is unavailable or invalid."""


@dataclass(frozen=True)
class PerformanceSeries:
    points: tuple[tuple[str, float], ...]
    benchmark: tuple[tuple[str, float], ...] | None = None
    metrics: Mapping[str, float | int] = field(default_factory=dict)
    evidence_tier: str = ""
    methodology: Mapping[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def to_chart(self) -> SeriesChart:
        return SeriesChart("历史净值", self.points)

    def to_payload(self) -> dict[str, Any]:
        return {
            "series": [{"date": date, "nav": nav} for date, nav in self.points],
            "benchmark": (
                None
                if self.benchmark is None
                else [{"date": date, "nav": nav} for date, nav in self.benchmark]
            ),
            "metrics": dict(self.metrics or {}),
            "evidence_tier": self.evidence_tier,
            "methodology": dict(self.methodology or {}),
            "limitations": list(self.limitations),
        }


def _canonical(payload: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _points(rows: Any, report_date: str, label: str) -> tuple[tuple[str, float], ...]:
    if not isinstance(rows, list) or len(rows) < 2:
        raise PerformanceArtifactError(f"{label} requires at least two points")
    points = []
    for row in rows:
        try:
            date = str(row["date"]).replace("-", "")
            value = float(row["nav"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PerformanceArtifactError(f"invalid {label} point") from exc
        if len(date) != 8 or not date.isdigit() or not math.isfinite(value) or value <= 0:
            raise PerformanceArtifactError(f"invalid {label} point")
        points.append((date, value))
    dates = [date for date, _ in points]
    if dates != sorted(dates) or dates[-1] > report_date or len(set(dates)) != len(dates):
        raise PerformanceArtifactError(f"invalid {label} dates")
    return tuple(points)


def _metadata(
    payload: Mapping[str, Any], points: tuple[tuple[str, float], ...]
) -> tuple[dict[str, float | int], str, dict[str, Any], tuple[str, ...]]:
    evidence_tier = payload.get("evidence_tier")
    if not isinstance(evidence_tier, str) or not evidence_tier.strip():
        raise PerformanceArtifactError("performance evidence tier is required")
    methodology = payload.get("methodology")
    if not isinstance(methodology, dict):
        raise PerformanceArtifactError("performance methodology is required")
    method = str(methodology.get("method", ""))
    if "proxy" in method and evidence_tier != "reconstructed_proxy":
        raise PerformanceArtifactError("proxy methodology requires reconstructed_proxy evidence")
    raw_metrics = payload.get("metrics")
    required = {
        "total_return",
        "annualized_return",
        "max_drawdown",
        "observations",
        "mean_turnover",
    }
    if not isinstance(raw_metrics, dict) or not required <= set(raw_metrics):
        raise PerformanceArtifactError("performance metrics are incomplete")
    metrics: dict[str, float | int] = {}
    for key in required:
        try:
            value = float(raw_metrics[key])
        except (TypeError, ValueError) as exc:
            raise PerformanceArtifactError("performance metrics must be numeric") from exc
        if not math.isfinite(value):
            raise PerformanceArtifactError("performance metrics must be finite")
        metrics[key] = int(value) if key == "observations" else value
    observed_total = points[-1][1] / points[0][1] - 1.0
    if not math.isclose(float(metrics["total_return"]), observed_total, abs_tol=1e-8):
        raise PerformanceArtifactError("performance metrics do not reconcile with NAV")
    raw_limitations = methodology.get("limitations", payload.get("limitations", []))
    if not isinstance(raw_limitations, list):
        raise PerformanceArtifactError("performance limitations must be a list")
    return metrics, evidence_tier, methodology, tuple(str(item) for item in raw_limitations)


def load_performance(path: Path, *, report_date: str) -> PerformanceSeries:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PerformanceArtifactError("performance artifact unavailable") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "weekly_basket.performance.v1"
    ):
        raise PerformanceArtifactError("unsupported performance artifact schema")
    digest = str(payload.get("artifact_sha256", ""))
    if digest != hashlib.sha256(_canonical(payload)).hexdigest():
        raise PerformanceArtifactError("performance artifact hash mismatch")
    points = _points(payload.get("series"), report_date, "series")
    benchmark = payload.get("benchmark")
    benchmark_points = None if benchmark is None else _points(benchmark, report_date, "benchmark")
    if benchmark_points is not None and [d for d, _ in benchmark_points] != [d for d, _ in points]:
        raise PerformanceArtifactError("benchmark dates do not align")
    metrics, evidence_tier, methodology, limitations = _metadata(payload, points)
    first = points[0][1]
    normalized = tuple((date, value / first) for date, value in points)
    normalized_benchmark = None
    if benchmark_points is not None:
        first_benchmark = benchmark_points[0][1]
        normalized_benchmark = tuple(
            (date, value / first_benchmark) for date, value in benchmark_points
        )
    return PerformanceSeries(
        normalized,
        normalized_benchmark,
        metrics,
        evidence_tier,
        methodology,
        limitations,
    )


def performance_metrics(series: PerformanceSeries, *, report_date: str) -> tuple[Metric, ...]:
    points = series.points
    last = points[-1][1]
    metrics = [Metric("累计收益", (last / points[0][1] - 1.0) * 100, "%")]
    for label, window in (("近5期", 5), ("近21期", 21)):
        if len(points) >= window:
            metrics.append(Metric(label, (last / points[-window][1] - 1.0) * 100, "%"))
        else:
            metrics.append(Metric(label, "不可用"))
    metrics.append(Metric("截至", report_date))
    return tuple(metrics)


__all__ = [
    "PerformanceArtifactError",
    "PerformanceSeries",
    "load_performance",
    "performance_metrics",
]
