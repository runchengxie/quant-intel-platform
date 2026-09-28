from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_chart_artifact import audit_chart_artifact
from tests.test_chart_contract import public_chart, rehash


def test_audit_accepts_matching_public_chart(tmp_path: Path):
    data = tmp_path / "data"
    charts = data / "charts"
    charts.mkdir(parents=True)
    (data / "reports.json").write_text(
        json.dumps({"reports": [{"id": "2026-09-18-morning"}]}), encoding="utf-8"
    )
    (charts / "2026-09-18-morning.json").write_text(json.dumps(public_chart()), encoding="utf-8")
    assert audit_chart_artifact(tmp_path) == {"chart_count": 1, "report_ids": ["2026-09-18-morning"]}


def test_audit_rejects_wrong_identity_and_private_path(tmp_path: Path):
    data = tmp_path / "data"
    charts = data / "charts"
    charts.mkdir(parents=True)
    (data / "reports.json").write_text(
        json.dumps({"reports": [{"id": "2026-09-18-morning"}]}), encoding="utf-8"
    )
    (charts / "2026-09-18-evening.json").write_text(json.dumps(public_chart()), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        audit_chart_artifact(tmp_path)
    (charts / "2026-09-18-evening.json").unlink()
    chart = public_chart()
    chart["charts"][0]["points"][0]["label"] = "/home/private/raw"
    (charts / "2026-09-18-morning.json").write_text(json.dumps(rehash(chart)), encoding="utf-8")
    with pytest.raises(ValueError, match="private"):
        audit_chart_artifact(tmp_path)
