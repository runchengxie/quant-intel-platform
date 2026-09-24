"""An offline six-card candidate must be dated, bounded and fail closed."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from a_share_daily import cli
from a_share_daily.charts.public_export import export_candidate
from a_share_daily.evening_manifest import build_evening_manifest


def point(day: str = "2026-09-18") -> dict:
    return {
        "label": "测试指标",
        "value": 1.5,
        "unit": "%",
        "observation_date": day,
        "source_label": "测试来源",
        "source_url": "https://example.test/source",
    }


@pytest.fixture
def manifest_fixture() -> dict:
    return {
        "date": "20260918",
        "report_kind": "morning",
        "generated_at": "2026-09-19T07:00:00+08:00",
        "feishu_chat_id": "private-chat-target",
        "charts": {
            "ok": ["dashboard", "sentiment", "weekly_chart"],
            "degraded": ["moneyflow"],
            "failed": ["topic"],
            "skipped": [],
            "errors": {"topic": "private /home/richard/raw.json", "moneyflow": "20260918 缺失"},
            "paths": {
                "dashboard": "/home/richard/daily_dashboard.png",
                "topic": "/home/richard/placeholder.png",
            },
            "public_points": {
                "dashboard": [point()],
                "moneyflow": [point("2026-09-17")],
                "sentiment": [point()],
                "weekly_chart": [point()],
            },
        },
    }


def test_export_preserves_status_and_never_copies_private_paths(manifest_fixture: dict):
    output = export_candidate(manifest_fixture, date="20260918", kind="morning")
    status = {card["key"]: card["status"] for card in output["charts"]}
    assert status == {
        "dashboard": "ok",
        "moneyflow": "degraded",
        "topic": "missing",
        "sentiment": "ok",
        "us_overnight": "missing",
        "weekly_chart": "ok",
    }
    assert output["charts"][1]["points"][0]["observation_date"] == "2026-09-17"
    text = json.dumps(output)
    assert "/home/" not in text
    assert "private-chat-target" not in text
    canonical = json.dumps(
        {key: value for key, value in output.items() if key != "content_sha256"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    assert output["content_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_evening_export_has_separate_identity(manifest_fixture: dict):
    morning = export_candidate(manifest_fixture, date="20260918", kind="morning")
    evening_manifest = build_evening_manifest(manifest_fixture, expected_date="20260918")
    evening = export_candidate(evening_manifest, date="20260918", kind="evening")
    assert morning["report_id"] == "2026-09-18-morning"
    assert evening["report_id"] == "2026-09-18-evening"
    assert evening["content_sha256"] != morning["content_sha256"]
    assert len(evening["charts"]) == 6
    assert evening["charts"][3]["title"] == "市场温度计"


def test_export_rejects_wrong_date_kind_and_non_object(manifest_fixture: dict):
    with pytest.raises(ValueError, match="date"):
        export_candidate(manifest_fixture, date="20260919", kind="morning")
    with pytest.raises(ValueError, match="kind"):
        export_candidate(manifest_fixture, date="20260918", kind="evening")
    with pytest.raises(ValueError, match="manifest"):
        export_candidate([], date="20260918", kind="morning")


def test_chart_candidate_cli_writes_only_to_external_path(
    tmp_path: Path,
    manifest_fixture: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    manifest_path = tmp_path / "morning.json"
    output_path = tmp_path / "2026-09-18-morning.json"
    manifest_path.write_text(json.dumps(manifest_fixture), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "a-share-daily",
            "chart-candidate",
            "--manifest",
            str(manifest_path),
            "--out",
            str(output_path),
            "--date",
            "20260918",
            "--kind",
            "morning",
        ],
    )
    cli.main()
    assert capsys.readouterr().out.strip() == str(output_path)
    assert json.loads(output_path.read_text(encoding="utf-8"))["publication"] == "candidate"

    repo_output = Path(__file__).resolve().parents[2] / "should-not-exist.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "a-share-daily",
            "chart-candidate",
            "--manifest",
            str(manifest_path),
            "--out",
            str(repo_output),
            "--date",
            "20260918",
            "--kind",
            "morning",
        ],
    )
    with pytest.raises(SystemExit, match="1"):
        cli.main()
    assert not repo_output.exists()
