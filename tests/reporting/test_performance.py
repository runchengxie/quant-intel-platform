from __future__ import annotations

import hashlib
import json

import pytest

from a_share_daily.reporting.performance import (
    PerformanceArtifactError,
    load_performance,
    performance_metrics,
)


def _write(path, *, series=None, **overrides):
    payload = {
        "schema_version": "weekly_basket.performance.v1",
        "report_date": "20260911",
        "status": "ok",
        "evidence_tier": "reconstructed_proxy",
        "series": series
        or [
            {"date": "2026-09-01", "nav": 1.0},
            {"date": "2026-09-11", "nav": 1.1},
        ],
        "benchmark": [
            {"date": "2026-09-01", "nav": 1.0},
            {"date": "2026-09-11", "nav": 1.03},
        ],
        "metrics": {
            "total_return": 0.1,
            "annualized_return": 0.2,
            "max_drawdown": -0.05,
            "observations": 2,
            "mean_turnover": 0.1,
        },
        "methodology": {
            "method": "weekly_64_reconstructed_pit_proxy",
            "cost_bps": 10.0,
            "limitations": ["period_return_replay"],
        },
        "artifact_sha256": "",
    }
    payload.update(overrides)
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
    assert series.benchmark is not None
    assert series.evidence_tier == "reconstructed_proxy"
    assert series.metrics["annualized_return"] == pytest.approx(0.2)
    assert series.methodology["cost_bps"] == pytest.approx(10.0)
    assert series.limitations == ("period_return_replay",)
    assert performance_metrics(series, report_date="20260911")[0].value == pytest.approx(10.0)


def test_load_performance_rejects_short_series(tmp_path):
    path = tmp_path / "performance.json"
    _write(path, series=[{"date": "2026-09-01", "nav": 1.0}])

    with pytest.raises(PerformanceArtifactError):
        load_performance(path, report_date="20260911")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"evidence_tier": None}, "evidence"),
        ({"evidence_tier": "official"}, "proxy"),
        ({"metrics": {"total_return": 0.5}}, "metrics"),
        (
            {
                "series": [
                    {"date": "2026-09-01", "nav": 1.0},
                    {"date": "2026-09-12", "nav": 1.1},
                ]
            },
            "dates",
        ),
    ],
)
def test_load_performance_rejects_untrustworthy_proxy(tmp_path, overrides, message):
    path = tmp_path / "performance.json"
    _write(path, **overrides)

    with pytest.raises(PerformanceArtifactError, match=message):
        load_performance(path, report_date="20260911")
