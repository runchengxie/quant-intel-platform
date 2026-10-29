"""Active evening reports consume pinned retrospective evidence without forecasting."""

import hashlib
import json
from pathlib import Path

import pytest
from test_overseas_theme_evidence import evidence as evidence_fixture

from a_share_daily import cli
from a_share_daily.review import renderers

evidence = evidence_fixture


def _payload():
    return {
        key: {} for key in ("indices", "overview", "limits", "moneyflow", "margin", "hot_sectors")
    } | {
        "overview": {"breadth": {"up": 0, "down": 0, "flat": 0}},
        "industry_stats": [],
        "top_amount_stocks": [],
    }


@pytest.fixture
def pinned(tmp_path, request):
    evidence = request.getfixturevalue("evidence")
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_evening_json_preserves_negative_evidence_and_absence(monkeypatch, pinned):
    monkeypatch.setattr(renderers, "build_review_payload", lambda _: _payload())
    path, sha = pinned
    result = json.loads(renderers.build_json("20261029", evidence_path=path, evidence_sha256=sha))
    section = result["overseas_theme_research"]
    assert section["status"] == "available"
    assert section["evidence"]["comparisons"][0]["mse_gain"] == -0.1
    assert section["evidence"]["historical_pit_certified"] is False
    absent = json.loads(renderers.build_json("20261029"))["overseas_theme_research"]
    assert absent["rejection"] == "not_supplied"


@pytest.mark.parametrize(
    ("date", "sha", "reason"),
    [("20261027", None, "future_generated"), ("20261029", "0" * 64, "hash_mismatch")],
)
def test_evening_rejects_future_or_changed_evidence(monkeypatch, pinned, date, sha, reason):
    monkeypatch.setattr(renderers, "build_review_payload", lambda _: _payload())
    path, actual = pinned
    result = json.loads(
        renderers.build_json(date, evidence_path=path, evidence_sha256=sha or actual)
    )
    assert result["overseas_theme_research"]["rejection"] == reason
    assert result["overseas_theme_research"]["evidence"] is None


def test_evening_markdown_uses_existing_localized_caveats(monkeypatch, pinned):
    monkeypatch.setattr(renderers, "build_review_payload", lambda _: _payload())
    path, sha = pinned
    report = renderers.build_report("20261029", evidence_path=path, evidence_sha256=sha)
    assert "回溯探索性研究" in report
    assert "-0.1" in report
    assert "Current constituents" in report


def test_evening_cli_env_pin_and_explicit_override(monkeypatch):
    monkeypatch.setenv("OVERSEAS_THEME_EVIDENCE_PATH", "/reviewed.json")
    monkeypatch.setenv("OVERSEAS_THEME_EVIDENCE_SHA256", "a" * 64)
    parser = cli._build_parser()
    args = parser.parse_args(["evening", "--date", "20261029"])
    assert args.overseas_theme_evidence == Path("/reviewed.json")
    assert args.overseas_theme_sha256 == "a" * 64
    assert args.send_feishu is False
    args = parser.parse_args(["review", "--overseas-theme-sha256", "b" * 64])
    assert args.overseas_theme_sha256 == "b" * 64


def test_absent_markdown_keeps_explicit_not_supplied(monkeypatch):
    monkeypatch.setattr(renderers, "build_review_payload", lambda _: _payload())
    report = renderers.build_report("20261029")
    assert "not_supplied" in report
    assert "schema_invalid" not in report


@pytest.mark.parametrize("json_output", [True, False])
def test_cli_forwards_reviewed_pin_without_delivery(monkeypatch, pinned, capsys, json_output):
    from a_share_daily import review

    monkeypatch.setenv("OVERSEAS_THEME_EVIDENCE_PATH", str(pinned[0]))
    monkeypatch.setenv("OVERSEAS_THEME_EVIDENCE_SHA256", pinned[1])
    calls = []

    def build(date, **kwargs):
        calls.append((date, kwargs))
        return "reviewed output"

    monkeypatch.setattr(review, "build_json", build)
    monkeypatch.setattr(review, "build_report", build)
    args = cli._build_parser().parse_args(
        ["evening", "--date", "20261029"] + (["--json"] if json_output else [])
    )
    assert cli._cmd_evening_review(args) is None
    assert calls[0][1]["evidence_path"] == pinned[0]
    assert calls[0][1]["evidence_sha256"] == pinned[1]
    assert "reviewed output" in capsys.readouterr().out


@pytest.mark.parametrize("missing", ["path", "sha"])
def test_partial_pin_never_loads_evidence(monkeypatch, pinned, missing):
    monkeypatch.setattr(renderers, "build_review_payload", lambda _: _payload())
    path, sha = pinned
    result = json.loads(
        renderers.build_json(
            "20261029",
            evidence_path=None if missing == "path" else path,
            evidence_sha256=None if missing == "sha" else sha,
        )
    )["overseas_theme_research"]
    assert result["evidence"] is None
    assert result["rejection"] == ("unreadable" if missing == "path" else "invalid_pin")


def test_future_report_date_cannot_advance_actual_cutoff(monkeypatch, pinned):
    from datetime import UTC, datetime

    from a_share_daily import overseas_theme_report

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 27, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(overseas_theme_report, "datetime", FrozenDatetime)
    result = overseas_theme_report.evening_evidence("20261101", *pinned)
    assert result["rejection"] == "future_generated"
    assert result["evidence_cutoff_utc"] == "2026-10-27T12:00:00+00:00"
