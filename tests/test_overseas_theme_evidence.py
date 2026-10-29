"""Pinned evidence consumption must fail closed without suppressing negative findings."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from a_share_daily.overseas_theme_report import render_evidence
from research_contracts.overseas_theme import EvidenceError, load_evidence


@pytest.fixture
def evidence():
    return {
        "schema_version": "overseas_theme_evidence.v1",
        "study_id": "semiconductors",
        "generated_at_utc": "2026-10-28T00:00:00Z",
        "source_revision": "a" * 40,
        "decision_time_local": "08:45",
        "decision_timezone": "Asia/Shanghai",
        "evidence_status": "retrospective_exploratory",
        "historical_pit_certified": False,
        "sample_start": "2020-01-01",
        "sample_end": "2026-10-27",
        "source_sha256": {"prices": "b" * 64},
        "sources": {"prices": {"url": "https://example.org/prices", "sha256": "b" * 64}},
        "comparisons": [
            {
                "evidence_id": "test-gap-0",
                "source_ids": ["prices"],
                "target": "index",
                "outcome": "gap",
                "lag_sessions": 0,
                "n": 20,
                "baseline": "mean",
                "augmented": "foreign",
                "mse_gain": -0.1,
                "mse_gain_ci95": [-0.3, 0.2],
            }
        ],
        "limitations": ["Current constituents; not historical point-in-time certified."],
    }


def consume(tmp_path, evidence, **kwargs):
    path = tmp_path / "evidence.json"
    payload = json.dumps(evidence).encode()
    path.write_bytes(payload)
    return load_evidence(
        path,
        kwargs.pop("sha", hashlib.sha256(payload).hexdigest()),
        kwargs.pop("at", datetime(2026, 10, 29, tzinfo=UTC)),
    )


def test_load_and_render_preserve_negative_evidence(tmp_path, evidence):
    loaded = consume(tmp_path, evidence)
    for locale in ("en-US", "zh-CN"):
        rendered = "\n".join(render_evidence(loaded, locale))
        assert "-0.1" in rendered
        assert "test-gap-0" in rendered
        assert "https://example.org/prices" in rendered
        assert "2020-01-01" in rendered
        assert "2026-10-28T00:00:00Z" in rendered


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("historical_pit_certified", True, "schema_invalid"),
        ("source_revision", "main", "schema_invalid"),
        ("generated_at_utc", "2026-10-30T00:00:00Z", "future_generated"),
        ("generated_at_utc", "2026-10-28T00:00:00", "invalid_timestamp"),
        ("sample_end", "2026-10-30", "sample_dates"),
        ("sample_start", "2026-10-28", "sample_dates"),
    ],
)
def test_reject_metadata(tmp_path, evidence, field, value, code):
    evidence[field] = value
    with pytest.raises(EvidenceError, match=f"^{code}$"):
        consume(tmp_path, evidence)


@pytest.mark.parametrize("mutation", ["hash", "url", "source_id", "nan", "interval", "boolean_n"])
def test_reject_bad_provenance_and_statistics(tmp_path, evidence, mutation):
    row = evidence["comparisons"][0]
    if mutation == "hash":
        evidence["sources"]["prices"]["sha256"] = "c" * 64
    elif mutation == "url":
        evidence["sources"]["prices"]["url"] = "file:///secret"
    elif mutation == "source_id":
        row["source_ids"] = ["unknown"]
    elif mutation == "nan":
        row["mse_gain"] = float("nan")
    elif mutation == "interval":
        row["mse_gain_ci95"] = [1.0, -1.0]
    else:
        row["n"] = True
    with pytest.raises(EvidenceError):
        consume(tmp_path, evidence)


def test_pin_and_clock_required(tmp_path, evidence):
    with pytest.raises(EvidenceError, match="^hash_mismatch$"):
        consume(tmp_path, evidence, sha="0" * 64)
    with pytest.raises(EvidenceError, match="^invalid_observed_at$"):
        consume(tmp_path, evidence, at=datetime(2026, 10, 29))


def test_visible_safe_degradation():
    assert "observations" in "\n".join(render_evidence(None)).lower()
    assert "hash_mismatch" in "\n".join(render_evidence(None, rejection="hash_mismatch"))
    assert "/secret" not in "\n".join(render_evidence(None, rejection="/secret"))


@pytest.mark.parametrize(
    "mutation", ["duplicate_id", "source_set", "empty_limits", "future_sample", "non_utc"]
)
def test_additional_contract_rejections(tmp_path, evidence, mutation):
    if mutation == "duplicate_id":
        evidence["comparisons"].append(evidence["comparisons"][0].copy())
    elif mutation == "source_set":
        evidence["source_sha256"]["extra"] = "e" * 64
    elif mutation == "empty_limits":
        evidence["limitations"] = []
    elif mutation == "future_sample":
        evidence["sample_end"] = "2026-10-29"
    else:
        evidence["generated_at_utc"] = "2026-10-28T00:00:00+08:00"
    with pytest.raises(EvidenceError):
        consume(tmp_path, evidence)


def test_missing_oversized_and_duplicate_json(tmp_path):
    path = tmp_path / "missing.json"
    at = datetime(2026, 10, 29, tzinfo=UTC)
    with pytest.raises(EvidenceError, match="^unreadable$"):
        load_evidence(path, "a" * 64, at)
    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(EvidenceError, match="^too_large$"):
        load_evidence(path, "a" * 64, at)
    payload = b'{"schema_version": 1, "schema_version": 2}'
    path.write_bytes(payload)
    with pytest.raises(EvidenceError, match="^invalid_json$"):
        load_evidence(path, hashlib.sha256(payload).hexdigest(), at)


@pytest.mark.parametrize("location", ["top", "source", "comparison"])
def test_unknown_fields_fail_closed(tmp_path, evidence, location):
    target = (
        evidence
        if location == "top"
        else (evidence["sources"]["prices"] if location == "source" else evidence["comparisons"][0])
    )
    target["private_research_notes"] = "unapproved material"
    with pytest.raises(EvidenceError, match="^schema_invalid$"):
        consume(tmp_path, evidence)


def test_embedded_schema_matches_contract():
    from pathlib import Path

    from research_contracts.overseas_theme import _SCHEMA

    schema_path = (
        Path(__file__).parents[1] / "docs/contracts/overseas_theme_evidence.v1.schema.json"
    )
    assert json.loads(schema_path.read_text()) == _SCHEMA


def test_unrepresentable_gain_rejected(tmp_path, evidence):
    evidence["comparisons"][0]["mse_gain"] = 10**1000
    with pytest.raises(EvidenceError, match="^comparison_invalid$"):
        consume(tmp_path, evidence)


def test_optional_nonfinite_statistics_rejected(tmp_path, evidence):
    evidence["comparisons"][0]["baseline_rmse_bp"] = float("inf")
    with pytest.raises(EvidenceError):
        consume(tmp_path, evidence)
