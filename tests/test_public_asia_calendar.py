"""Regression coverage for the public Asia calendar's holiday projection."""

import json
from pathlib import Path

from project_tools.export_public_asia_calendar import build_calendar

CONFIGS = Path(__file__).resolve().parents[1] / "web" / "configs"


def test_public_projection_matches_offline_source_and_retains_sse_provenance():
    sse = json.loads((CONFIGS / "a-share-calendar.json").read_text())
    projection = build_calendar(sse)
    assert projection == json.loads((CONFIGS / "asia-calendar.json").read_text())
    assert projection["source_sha256"] == sse["source_sha256"]
    assert projection["source_url"] == sse["source_url"]
    assert set(projection["days"]) == set(sse["days"])


def test_china_holiday_still_has_hong_kong_and_japan_sessions():
    calendar = json.loads((CONFIGS / "asia-calendar.json").read_text())
    assert calendar["markets"]["2026-10-05"] == ["HK", "JP"]
    assert calendar["days"]["2026-10-05"] is True
    assert calendar["markets"]["2026-10-04"] == []
    assert calendar["days"]["2026-10-04"] is False
