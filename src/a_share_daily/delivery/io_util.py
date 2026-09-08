"""IO utilities and chart-freshness helpers for A-share delivery.

Moved verbatim from ``report_delivery.py`` as a pure physical refactor.
All symbols here are re-exported from ``report_delivery`` to keep callers
and tests working unchanged.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _project_root() -> Path:
    configured = os.environ.get("MARKET_INTEL_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _project_root()

EVENING_CHARTS = (
    ("综合仪表盘", "daily_dashboard.png"),
    ("资金流向图", "daily_moneyflow_chart.png"),
    ("热点概念图", "daily_topic_chart.png"),
    ("市场温度计", "daily_sentiment_chart.png"),
    ("美股隔夜图", "daily_us_overnight.png"),
    ("周度概览图", "daily_weekly_chart.png"),
)
EVENING_CHART_KEYS = {
    "daily_dashboard.png": "dashboard",
    "daily_moneyflow_chart.png": "moneyflow",
    "daily_topic_chart.png": "topic",
    "daily_sentiment_chart.png": "sentiment",
    "daily_us_overnight.png": "us_overnight",
    "daily_weekly_chart.png": "weekly_chart",
}
MORNING_CHARTS = (
    ("综合仪表盘", "daily_dashboard.png"),
    ("资金流向图", "daily_moneyflow_chart.png"),
    ("热点概念图", "daily_topic_chart.png"),
    ("情绪指标图", "daily_sentiment_chart.png"),
    ("美股隔夜图", "daily_us_overnight.png"),
    ("周度概览图", "daily_weekly_chart.png"),
)
MORNING_CHART_KEYS = {
    "daily_dashboard.png": "dashboard",
    "daily_moneyflow_chart.png": "moneyflow",
    "daily_topic_chart.png": "topic",
    "daily_sentiment_chart.png": "sentiment",
    "daily_us_overnight.png": "us_overnight",
    "daily_weekly_chart.png": "weekly_chart",
}


def _chart_stale_tolerance_seconds() -> float:
    raw = os.environ.get("A_SHARE_CHART_STALE_TOLERANCE_SECONDS", "1800").strip()
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return 1800.0


def _resolve_chart_path(raw_path: str, out_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path

    candidates = [
        path,
        PROJECT_ROOT / path,
        out_dir / path.name,
        out_dir / path,
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate.resolve()
    return out_dir / path


def _chart_is_fresh(path: Path, manifest_path: Path | None) -> bool:
    if manifest_path is None or not manifest_path.exists():
        return True
    try:
        chart_mtime = path.stat().st_mtime
        manifest_mtime = manifest_path.stat().st_mtime
    except OSError:
        return False
    if chart_mtime + _chart_stale_tolerance_seconds() < manifest_mtime:
        print(
            f"[report_delivery] chart stale relative to manifest, skipping: {path}",
            file=sys.stderr,
        )
        return False
    return True
