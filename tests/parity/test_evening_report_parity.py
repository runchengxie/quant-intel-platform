from a_share_daily.evening_manifest import build_evening_manifest


def test_evening_manifest_preserves_date_and_artifact_inventory() -> None:
    payload = {
        "date": "20260908",
        "charts": [
            {"name": "market_temperature", "status": "ready", "path": "charts/temp.png"},
            {"name": "capital_flow", "status": "degraded", "reason": "source missing"},
        ],
        "artifact_inventory": {"charts": 2, "report": "ready"},
    }

    manifest = build_evening_manifest(payload, expected_date="2026-09-08")

    assert manifest["pipeline"] == "evening"
    assert manifest["report_kind"] == "evening"
    assert manifest["source_pipeline"] == "morning_chart_generation"
    assert manifest["date"] == "20260908"
    assert manifest["charts"] == payload["charts"]
    assert manifest["artifact_inventory"] == payload["artifact_inventory"]


def test_evening_manifest_rejects_wrong_report_date() -> None:
    try:
        build_evening_manifest({"date": "20260907"}, expected_date="2026-09-08")
    except ValueError as exc:
        assert "manifest date" in str(exc)
    else:
        raise AssertionError("expected a date mismatch to be rejected")
