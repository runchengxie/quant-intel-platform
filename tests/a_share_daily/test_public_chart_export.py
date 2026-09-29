"""An offline six-card candidate must be dated, bounded and fail closed."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from a_share_daily import cli
from a_share_daily.charts.public_export import export_candidate
from a_share_daily.charts.public_extract import extract_evening_review_points
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
            "errors": {
                "topic": "private /home/richard/raw.json",
                "moneyflow": "moneyflow_ths 20260918 暂缺，使用最新可用 20260917",
            },
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
    assert evening["charts"][3]["status"] == "missing"
    assert evening["charts"][3]["points"] == []


def test_evening_review_points_use_hot_concept_top5_and_six_dimensions() -> None:
    review = {
        "date": "20260929",
        "hot_sectors": {
            "top_by_change": [
                {"name": "租售同权", "pct_change": 3.95},
                {"name": "房地产供改", "pct_change": 3.86},
                {"name": "AI营销", "pct_change": 3.83},
                {"name": "房地产开发", "pct_change": 3.81},
                {"name": "GEO概念", "pct_change": 3.41},
                {"name": "不应展示", "pct_change": 3.40},
            ]
        },
        "market_temperature": {
            "heat_score": 59.5,
            "fragility_score": 20.1,
            "dimensions": {
                "liquidity": {"label": "流动性", "score": 1.3},
                "breadth": {"label": "广度", "score": 60.4},
                "profit_effect": {"label": "赚钱效应", "score": 54.5},
                "loss_risk": {"label": "亏钱风险", "score": 7.7},
                "trend_confirmation": {"label": "趋势确认", "score": 76.4},
                "rotation_quality": {"label": "轮动质量", "score": 80.1},
            },
        },
    }

    points = extract_evening_review_points(review, "20260929")

    assert [item["label"] for item in points["topic"]] == [
        "租售同权",
        "房地产供改",
        "AI营销",
        "房地产开发",
        "GEO概念",
    ]
    assert [item["value"] for item in points["topic"]] == [3.95, 3.86, 3.83, 3.81, 3.41]
    assert [item["label"] for item in points["sentiment"]] == [
        "流动性",
        "广度",
        "赚钱效应",
        "亏钱风险",
        "趋势确认",
        "轮动质量",
    ]
    assert points["sentiment"][3]["unit"] == "观察分（风险）"
    assert points["sentiment"][0]["source_label"] == "Tushare A股晚报六维观察"


def test_evening_review_points_reject_wrong_date() -> None:
    with pytest.raises(ValueError, match="date"):
        extract_evening_review_points({"date": "20260928"}, "20260929")


def test_evening_manifest_promotes_review_points_to_public_candidate(
    manifest_fixture: dict,
) -> None:
    review = {
        "date": "20260918",
        "hot_sectors": {
            "top_by_change": [{"name": f"概念{i}", "pct_change": float(i)} for i in range(5, 0, -1)]
        },
        "market_temperature": {
            "dimensions": {
                key: {"label": label, "score": 50.0}
                for key, label in (
                    ("liquidity", "流动性"),
                    ("breadth", "广度"),
                    ("profit_effect", "赚钱效应"),
                    ("loss_risk", "亏钱风险"),
                    ("trend_confirmation", "趋势确认"),
                    ("rotation_quality", "轮动质量"),
                )
            }
        },
    }
    evening_manifest = build_evening_manifest(
        manifest_fixture, expected_date="20260918", review_payload=review
    )
    evening = export_candidate(evening_manifest, date="20260918", kind="evening")
    cards = {card["key"]: card for card in evening["charts"]}
    assert cards["topic"]["status"] == "ok"
    assert cards["topic"]["points"][0]["label"] == "概念5"
    assert cards["sentiment"]["status"] == "ok"
    assert len(cards["sentiment"]["points"]) == 6


def test_error_is_not_promoted_to_ok_even_with_retained_points(manifest_fixture: dict):
    manifest_fixture["charts"]["ok"].append("topic")
    manifest_fixture["charts"]["failed"].remove("topic")
    manifest_fixture["charts"]["public_points"]["topic"] = [point()]
    output = export_candidate(manifest_fixture, date="20260918", kind="morning")
    topic = next(card for card in output["charts"] if card["key"] == "topic")
    assert topic["status"] == "missing"
    assert topic["points"] == []


def test_arbitrary_moneyflow_error_is_not_treated_as_fallback(manifest_fixture: dict):
    manifest_fixture["charts"]["errors"]["moneyflow"] = "render failed"
    output = export_candidate(manifest_fixture, date="20260918", kind="morning")
    moneyflow = next(card for card in output["charts"] if card["key"] == "moneyflow")
    assert moneyflow["status"] == "missing"


def test_stale_moneyflow_cannot_be_ok_even_with_wrong_upstream_status(
    manifest_fixture: dict,
):
    manifest_fixture["charts"]["degraded"].remove("moneyflow")
    manifest_fixture["charts"]["ok"].append("moneyflow")
    manifest_fixture["charts"]["errors"].pop("moneyflow")
    output = export_candidate(manifest_fixture, date="20260918", kind="morning")
    moneyflow = next(card for card in output["charts"] if card["key"] == "moneyflow")
    assert moneyflow["status"] == "degraded"
    assert moneyflow["points"][0]["observation_date"] == "2026-09-17"


def test_partial_us_points_are_marked_degraded(manifest_fixture: dict):
    manifest_fixture["charts"]["ok"].append("us_overnight")
    manifest_fixture["charts"]["public_points"]["us_overnight"] = [point("2026-09-17")]
    output = export_candidate(manifest_fixture, date="20260918", kind="morning")
    us = next(card for card in output["charts"] if card["key"] == "us_overnight")
    assert us["status"] == "degraded"


def test_dashboard_with_margin_older_than_previous_turnover_session_is_degraded(
    manifest_fixture: dict,
):
    manifest_fixture["charts"]["public_points"]["dashboard"] = [
        {**point("2026-09-18"), "label": "上涨家数"},
        {**point("2026-09-17"), "label": "成交额 2026-09-17"},
        {**point("2026-09-18"), "label": "成交额 2026-09-18"},
        {**point("2026-09-14"), "label": "融资余额 2026-09-14"},
    ]
    output = export_candidate(manifest_fixture, date="20260918", kind="morning")
    dashboard = next(card for card in output["charts"] if card["key"] == "dashboard")
    assert dashboard["status"] == "degraded"
    assert "融资余额" in dashboard["reason"]


def test_export_rejects_wrong_date_kind_and_non_object(manifest_fixture: dict):
    with pytest.raises(ValueError, match="date"):
        export_candidate(manifest_fixture, date="20260919", kind="morning")
    with pytest.raises(ValueError, match="kind"):
        export_candidate(manifest_fixture, date="20260918", kind="evening")
    with pytest.raises(ValueError, match="manifest"):
        export_candidate([], date="20260918", kind="morning")


def test_candidate_cli_is_deterministic_and_whitelisted(
    tmp_path: Path, manifest_fixture: dict, monkeypatch: pytest.MonkeyPatch
):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_fixture), encoding="utf-8")
    outputs = [tmp_path / "one.json", tmp_path / "two.json"]
    for output in outputs:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "a-share-daily",
                "chart-candidate",
                "--manifest",
                str(manifest_path),
                "--out",
                str(output),
                "--date",
                "20260918",
                "--kind",
                "morning",
            ],
        )
        cli.main()
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    candidate = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert set(candidate) == {
        "schema_version",
        "publication",
        "report_id",
        "date",
        "kind",
        "generated_at",
        "charts",
        "content_sha256",
    }
    assert "feishu_chat_id" not in outputs[0].read_text(encoding="utf-8")
    assert "/home/" not in outputs[0].read_text(encoding="utf-8")


def test_invalid_point_does_not_overwrite_existing_candidate(
    tmp_path: Path, manifest_fixture: dict, monkeypatch: pytest.MonkeyPatch
):
    manifest_fixture["charts"]["public_points"]["dashboard"][0]["value"] = float("inf")
    manifest_path = tmp_path / "bad.json"
    output = tmp_path / "candidate.json"
    output.write_text("previous reviewed candidate", encoding="utf-8")
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
            str(output),
            "--date",
            "20260918",
            "--kind",
            "morning",
        ],
    )
    with pytest.raises(SystemExit, match="1"):
        cli.main()
    assert output.read_text(encoding="utf-8") == "previous reviewed candidate"


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
