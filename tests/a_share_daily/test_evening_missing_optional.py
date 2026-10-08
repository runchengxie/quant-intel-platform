import pandas as pd
import pytest

from a_share_daily.charts.public_export import export_candidate
from a_share_daily.charts.public_extract import extract_evening_review_points
from a_share_daily.evening_manifest import build_evening_manifest
from a_share_daily.review.loaders import load_hot_sectors


def review():
    return {
        "trade_date": "20261008",
        "hot_sectors": {},
        "market_temperature": {
            "dimensions": {
                key: {"label": key, "score": 50.0}
                for key in (
                    "liquidity",
                    "breadth",
                    "profit_effect",
                    "loss_risk",
                    "trend_confirmation",
                    "rotation_quality",
                )
            }
        },
    }


@pytest.mark.parametrize("absent", [True, False])
def test_absent_optional_topic_is_missing_and_keeps_verified_temperature(absent):
    payload = review()
    if absent:
        payload.pop("hot_sectors")
    source = {
        "date": "20261008",
        "generated_at": "2026-10-08T19:00:00+08:00",
        "charts": {
            "ok": ["topic"],
            "degraded": ["topic"],
            "failed": ["sentiment"],
            "skipped": [],
            "errors": {"topic": "old provider error"},
            "public_points": {"topic": [{"stale": "must not survive"}]},
        },
    }
    manifest = build_evening_manifest(source, expected_date="20261008", review_payload=payload)
    assert "topic" not in manifest["charts"]["ok"]
    assert "topic" not in manifest["charts"]["degraded"]
    assert manifest["charts"]["missing"] == ["topic"]
    assert manifest["charts"]["public_points"]["topic"] == []
    cards = {
        card["key"]: card
        for card in export_candidate(manifest, date="20261008", kind="evening")["charts"]
    }
    assert cards["topic"]["status"] == "missing"
    assert cards["topic"]["reason"] == "当日概念板块数据暂缺"
    assert cards["topic"]["points"] == []
    assert cards["sentiment"]["status"] == "ok"
    assert len(cards["sentiment"]["points"]) == 6
    assert source["charts"]["public_points"]["topic"] == [{"stale": "must not survive"}]


@pytest.mark.parametrize(
    "sectors",
    [
        None,
        [],
        {"wrong_key": []},
        {"top_by_change": None},
        {"top_by_change": []},
        {"top_by_change": [{"name": "x", "pct_change": 1.0}] * 4},
        {"top_by_change": [{"name": "x", "pct_change": "invalid"}] * 5},
        {"top_by_change": [{"name": "x", "pct_change": float("nan")}] * 5},
    ],
)
def test_malformed_or_partial_topic_still_blocks(sectors):
    payload = review()
    payload["hot_sectors"] = sectors
    with pytest.raises((ValueError, KeyError)):
        extract_evening_review_points(payload, "20261008")


def test_missing_required_temperature_still_blocks():
    payload = review()
    payload["market_temperature"] = {}
    with pytest.raises(ValueError):
        extract_evening_review_points(payload, "20261008")


@pytest.mark.parametrize("case", ["missing_file", "empty", "corrupt", "schema"])
def test_optional_concept_loader_distinguishes_missing_from_malformed(monkeypatch, case):
    def read(day):
        assert day == "20261008"
        if case == "missing_file":
            raise FileNotFoundError("missing")
        if case == "corrupt":
            raise ValueError("broken parquet")
        return pd.DataFrame() if case == "empty" else pd.DataFrame({"wrong_column": [1]})

    monkeypatch.setattr("a_share_daily.review.loaders.D.read_dc_concept", read)
    if case in {"missing_file", "empty"}:
        assert load_hot_sectors("20261008") == {}
    else:
        with pytest.raises(ValueError, match="invalid concept sector input"):
            load_hot_sectors("20261008")
