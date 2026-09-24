"""The candidate boundary must not publish unverified chart observations."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from a_share_daily.charts.public_contract import CHART_KEYS, build_candidate, write_candidate


def cards() -> dict[str, dict]:
    result = {
        key: {"key": key, "title": key, "status": "missing", "reason": "无当日数据", "points": []}
        for key in CHART_KEYS
    }
    result["moneyflow"] = {
        "key": "moneyflow",
        "title": "资金流向",
        "status": "ok",
        "points": [
            {
                "label": "样例",
                "value": 1.1,
                "unit": "亿元",
                "observation_date": "2026-09-18",
                "source_label": "测试数据",
                "source_url": "https://example.test/source",
            }
        ],
    }
    return result


def candidate(cards_value: dict[str, dict] | None = None) -> dict:
    return build_candidate(
        "2026-09-18", "morning", cards_value or cards(), "2026-09-19T07:00:00+08:00"
    )


def test_candidate_has_six_ordered_cards_and_a_stable_hash():
    output = candidate()
    assert output["report_id"] == "2026-09-18-morning"
    assert [card["key"] for card in output["charts"]] == list(CHART_KEYS)
    assert output["publication"] == "candidate"
    assert len(output["content_sha256"]) == 64
    assert output == candidate()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"value": float("inf")}, "finite"),
        ({"source_url": ""}, "source_url"),
        ({"observation_date": "2026-09-31"}, "observation_date"),
        ({"label": "/home/richard/private"}, "private"),
        ({"source_label": "api_key=private-value"}, "secret"),
        ({"source_url": "https://localhost/source"}, "public HTTPS"),
    ],
)
def test_candidate_rejects_unverified_points(change: dict, message: str):
    value = cards()
    value["moneyflow"]["points"][0].update(change)
    with pytest.raises(ValueError, match=message):
        candidate(value)


def test_candidate_rejects_missing_card_that_claims_a_point():
    value = cards()
    value["dashboard"]["points"] = copy.deepcopy(value["moneyflow"]["points"])
    with pytest.raises(ValueError, match="missing"):
        candidate(value)


def test_candidate_whitelists_fields_and_rejects_missing_key():
    value = cards()
    value["moneyflow"]["private_path"] = "/home/richard/secret.png"
    assert "private_path" not in json.dumps(candidate(value))
    del value["topic"]
    with pytest.raises(ValueError, match="six"):
        candidate(value)


def test_candidate_rejects_invalid_date_and_kind():
    with pytest.raises(ValueError, match="date"):
        build_candidate("2026-09-31", "morning", cards(), "2026-09-19T07:00:00+08:00")
    with pytest.raises(ValueError, match="kind"):
        build_candidate("2026-09-18", "night", cards(), "2026-09-19T07:00:00+08:00")


def test_write_candidate_is_atomic_and_outside_repository(tmp_path: Path):
    path = tmp_path / "candidate.json"
    write_candidate(path, candidate())
    assert json.loads(path.read_text(encoding="utf-8"))["report_id"] == "2026-09-18-morning"
    with pytest.raises(ValueError, match="repository"):
        write_candidate(Path(__file__).resolve().parents[2] / "candidate.json", candidate())


def test_writer_refuses_modified_candidate_payload(tmp_path: Path):
    payload = candidate()
    payload["private_path"] = "/home/richard/secret.json"
    with pytest.raises(ValueError, match="candidate"):
        write_candidate(tmp_path / "bad.json", payload)
    assert not (tmp_path / "bad.json").exists()
