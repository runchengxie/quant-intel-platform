"""Only explicitly reviewed six-card snapshots cross the Pages boundary."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from scripts.chart_contract import CHART_KEYS, validate_public_chart


def public_chart() -> dict:
    cards = [
        {"key": key, "title": key, "status": "missing", "reason": "无已审核来源", "points": []}
        for key in CHART_KEYS
    ]
    cards[0] = {
        "key": "dashboard",
        "title": "综合仪表盘",
        "status": "ok",
        "reason": None,
        "points": [
            {
                "label": "上涨家数",
                "value": 100.0,
                "unit": "家",
                "observation_date": "2026-09-18",
                "source_label": "测试来源",
                "source_url": "https://example.test/source",
            }
        ],
    }
    payload = {
        "schema_version": "market_intel.a_share_charts.v1",
        "publication": "public",
        "report_id": "2026-09-18-morning",
        "date": "2026-09-18",
        "kind": "morning",
        "generated_at": "2026-09-19T07:00:00+08:00",
        "charts": cards,
    }
    return rehash(payload)


def rehash(payload: dict) -> dict:
    payload = deepcopy(payload)
    payload.pop("content_sha256", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def test_valid_public_chart_is_accepted():
    payload = public_chart()
    assert validate_public_chart(payload, expected_id="2026-09-18-morning") == payload


def test_valid_integer_point_keeps_its_verified_content_hash():
    payload = public_chart()
    payload["charts"][0]["points"][0]["value"] = 100
    payload = rehash(payload)
    validated = validate_public_chart(payload)
    assert validated == payload
    assert validate_public_chart(validated) == payload


@pytest.mark.parametrize(
    "change,message",
    [
        (lambda p: p.update(publication="candidate"), "public"),
        (lambda p: p.update(private_path="/home/richard/raw.png"), "field"),
        (lambda p: p.update(content_sha256="0" * 64), "hash"),
        (lambda p: p["charts"][0]["points"][0].update(value=float("inf")), "finite"),
        (
            lambda p: p["charts"][0]["points"][0].update(source_url="https://localhost/private"),
            "public HTTPS",
        ),
        (lambda p: p["charts"][1].update(points=[p["charts"][0]["points"][0]]), "missing"),
        (lambda p: p.update(report_id="2026-09-18-evening"), "report_id"),
    ],
)
def test_invalid_chart_is_rejected_even_with_recomputed_hash(change, message):
    payload = public_chart()
    change(payload)
    if message != "hash":
        payload = rehash(payload)
    with pytest.raises(ValueError, match=message):
        validate_public_chart(payload)


def test_cross_report_identity_is_rejected():
    with pytest.raises(ValueError, match="identity"):
        validate_public_chart(public_chart(), expected_id="2026-09-18-evening")
