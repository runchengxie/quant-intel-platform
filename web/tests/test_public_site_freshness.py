"""Runtime checks for the two public Pages report snapshots."""

import io
import json
from datetime import datetime
from urllib.error import URLError

import pytest

from scripts.public_site_freshness import evaluate_public_snapshots, fetch_public_snapshots

NOW = datetime.fromisoformat("2026-09-30T12:00:00+08:00")


def asia(day="2026-09-29", generated="2026-09-29 20:00:00"):
    return {
        "reports": [
            {
                "id": f"{day}-evening",
                "date": day,
                "kind": "evening",
                "sections": [{"paragraphs": [f"生成时间: {generated}", "private report body"]}],
            }
        ]
    }


def us(day="2026-09-29", generated="2026-09-30T07:00:00+08:00"):
    return {"run_id": f"daily-{day}", "generated_at": generated, "sections": ["private body"]}


def findings(reports=None, us_report=None, now=NOW):
    return {
        item["key"]: item
        for item in evaluate_public_snapshots(
            asia() if reports is None else reports,
            us() if us_report is None else us_report,
            now=now,
        )
    }


def test_fresh_reports_are_healthy_and_summaries_exclude_report_content():
    result = findings()
    assert set(result) == {"asia", "us"}
    assert {item["status"] for item in result.values()} == {"ok"}
    assert all(set(item) == {"key", "status", "summary"} for item in result.values())
    assert all("private" not in item["summary"] for item in result.values())


@pytest.mark.parametrize(
    ("reports", "us_report", "expected_key"),
    [
        (asia("2026-09-24", "2026-09-30 08:00:00"), us(), "asia"),
        (asia(), us("2026-09-24", "2026-09-30T08:00:00+08:00"), "us"),
        (asia("2026-09-29", "2026-09-25 08:00:00"), us(), "asia"),
        (asia(), us("2026-09-29", "2026-09-25T08:00:00+08:00"), "us"),
    ],
)
def test_old_market_date_or_generation_requires_review(reports, us_report, expected_key):
    result = findings(reports, us_report)
    assert result[expected_key]["status"] == "review"
    assert "review" in result[expected_key]["summary"].lower()
    assert "failed" not in result[expected_key]["summary"].lower()


@pytest.mark.parametrize("generated", ["garbage", "2026-09-30T08:00:00", "2026-10-01T08:00:00+08:00"])
def test_us_invalid_generation_cannot_be_fresh(generated):
    assert findings(us_report=us(generated=generated))["us"]["status"] == "unavailable"


@pytest.mark.parametrize("day", ["wrong", "2026-10-01"])
def test_us_invalid_or_future_market_date_cannot_be_fresh(day):
    assert findings(us_report=us(day=day))["us"]["status"] == "unavailable"


@pytest.mark.parametrize("day", ["wrong", "2026-10-01"])
def test_asia_invalid_or_future_market_date_cannot_be_fresh(day):
    assert findings(reports=asia(day=day))["asia"]["status"] == "unavailable"


@pytest.mark.parametrize("generated", ["bad", "2026-10-01 08:00:00"])
def test_asia_invalid_or_future_generation_cannot_be_fresh(generated):
    assert findings(reports=asia(generated=generated))["asia"]["status"] == "unavailable"


def test_missing_evening_and_missing_us_report_are_unavailable():
    morning = asia()["reports"][0] | {"kind": "morning"}
    result = findings({"reports": [morning]}, {})
    assert result["asia"]["status"] == "unavailable"
    assert result["us"]["status"] == "unavailable"


@pytest.mark.parametrize("row", [{"kind": "evening"}, {"kind": "evening", "date": "bad"}, "broken"])
def test_malformed_asia_row_is_a_bounded_availability_finding(row):
    result = findings({"reports": [row]}, us())
    assert result["asia"]["status"] == "unavailable"
    assert set(result["asia"]) == {"key", "status", "summary"}
    assert result["us"]["status"] == "ok"


def test_new_morning_does_not_mask_old_evening_report():
    old = asia("2026-09-24", "2026-09-24 20:00:00")["reports"][0]
    morning = asia()["reports"][0] | {"kind": "morning"}
    assert findings({"reports": [old, morning]})["asia"]["status"] == "review"


def test_long_market_closure_warns_for_review_without_claiming_publication_failed():
    result = findings(now=datetime.fromisoformat("2026-10-05T12:00:00+08:00"))
    assert {item["status"] for item in result.values()} == {"review"}
    assert all("review" in item["summary"].lower() for item in result.values())
    assert all("failed" not in item["summary"].lower() for item in result.values())


def test_naive_check_time_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        findings(now=datetime(2026, 9, 30, 12))


def test_fetch_uses_only_fixed_pages_urls_and_bounded_reads(monkeypatch):
    seen = []

    class Response(io.BytesIO):
        def read(self, size=-1):
            assert size == 1001
            return super().read(size)

    def open_url(request, timeout):
        seen.append((request.full_url, timeout))
        payload = asia() if request.full_url.endswith("/reports.json") else us()
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr("scripts.public_site_freshness.urlopen", open_url)
    reports, us_report = fetch_public_snapshots("https://example.test/project/", max_bytes=1000)
    assert reports == asia()
    assert us_report == us()
    assert seen == [
        ("https://example.test/project/data/reports.json", 10),
        ("https://example.test/project/data/market_daily_report.json", 10),
    ]


@pytest.mark.parametrize("fault", ["network", "oversize", "json", "array"])
def test_fetch_failure_yields_availability_finding_without_exposing_response(monkeypatch, fault):
    secret = "sensitive response content"

    def open_url(request, timeout):
        if request.full_url.endswith("/reports.json"):
            if fault == "network":
                raise URLError(secret)
            payload = {"oversize": secret * 50} if fault == "oversize" else None
            raw = (
                json.dumps(payload).encode()
                if payload
                else (b"{" + secret.encode() if fault == "json" else b"[]")
            )
            return io.BytesIO(raw)
        return io.BytesIO(json.dumps(us()).encode())

    monkeypatch.setattr("scripts.public_site_freshness.urlopen", open_url)
    reports, us_report = fetch_public_snapshots("https://example.test/project", max_bytes=200)
    result = findings(reports, us_report)
    assert result["asia"]["status"] == "unavailable"
    assert result["us"]["status"] == "ok"
    assert all(secret not in item["summary"] for item in result.values())


@pytest.mark.parametrize(
    "base", ["http://example.test", "https://example.test/?q=x", "https://user:pass@example.test"]
)
def test_fetch_rejects_non_pages_base(base):
    with pytest.raises(ValueError):
        fetch_public_snapshots(base)
