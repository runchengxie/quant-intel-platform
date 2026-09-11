from __future__ import annotations

import hashlib
import json

import pytest

from a_share_daily.reporting.performance import (
    PerformanceArtifactError,
    load_performance,
    performance_metrics,
)


def _write(path, *, series=None):
    payload = {
        "schema_version": "weekly_basket.performance.v1",
        "report_date": "20260911",
        "source": "test",
        "series": series
        or [
            {"date": "20260901", "nav": 1.0},
            {"date": "20260911", "nav": 1.1},
        ],
        "artifact_sha256": "",
    }
    unsigned = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    payload["artifact_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_performance_normalizes_and_builds_chart(tmp_path):
    path = tmp_path / "performance.json"
    _write(path)
    series = load_performance(path, report_date="20260911")

    assert series.points[0] == ("20260901", 1.0)
    assert series.to_chart().points[-1] == ("20260911", 1.1)
    assert performance_metrics(series, report_date="20260911")[0].value == pytest.approx(10.0)


def test_load_performance_rejects_short_series(tmp_path):
    path = tmp_path / "performance.json"
    _write(path, series=[{"date": "20260901", "nav": 1.0}])

    with pytest.raises(PerformanceArtifactError):
        load_performance(path, report_date="20260911")
