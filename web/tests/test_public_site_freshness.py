"""Runtime checks for the two public Pages report snapshots."""

import io
import json
from datetime import datetime
from email.message import Message
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import HTTPSHandler, Request, build_opener
from urllib.response import addinfourl

import pytest

from scripts import public_site_freshness
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


def test_asia_generation_just_over_96_hours_requires_review():
    result = findings(reports=asia(generated="2026-09-26 11:59:59"))
    assert result["asia"]["status"] == "review"


def test_asia_generation_one_second_in_future_is_unavailable():
    result = findings(reports=asia(generated="2026-09-30 12:00:01"))
    assert result["asia"]["status"] == "unavailable"


def test_naive_check_time_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        findings(now=datetime(2026, 9, 30, 12))


def test_fetch_uses_only_fixed_pages_urls_and_bounded_reads(monkeypatch):
    seen = []

    class Response(io.BytesIO):
        def __init__(self, payload, url):
            super().__init__(payload)
            self.url = url

        def geturl(self):
            return self.url

        def read(self, size=-1):
            assert size == 1001
            return super().read(size)

    def open_url(request, timeout):
        seen.append((request.full_url, timeout))
        payload = asia() if request.full_url.endswith("/reports.json") else us()
        return Response(json.dumps(payload).encode(), request.full_url)

    monkeypatch.setattr(
        public_site_freshness, "build_opener", lambda *handlers: SimpleNamespace(open=open_url)
    )
    reports, us_report = fetch_public_snapshots("https://example.test/project/", max_bytes=1000)
    assert reports == asia()
    assert us_report == us()
    assert seen == [
        ("https://example.test/project/data/reports.json", 10),
        ("https://example.test/project/data/market_daily_report.json", 10),
    ]


@pytest.mark.parametrize("redirected_name", ["reports.json", "market_daily_report.json"])
def test_redirected_snapshot_is_unavailable_before_response_body_is_read(monkeypatch, redirected_name):
    class RedirectResponse(io.BytesIO):
        def geturl(self):
            return "https://other.example.test/sensitive.json"

        def read(self, size=-1):
            pytest.fail("redirected response body must not be read")

    class OriginalResponse(io.BytesIO):
        def __init__(self, payload, url):
            super().__init__(payload)
            self.url = url

        def geturl(self):
            return self.url

    def open_url(request, timeout):
        if request.full_url.endswith("/" + redirected_name):
            return RedirectResponse(b"private body")
        payload = asia() if request.full_url.endswith("/reports.json") else us()
        return OriginalResponse(json.dumps(payload).encode(), request.full_url)

    monkeypatch.setattr(
        public_site_freshness, "build_opener", lambda *handlers: SimpleNamespace(open=open_url)
    )
    reports, us_report = fetch_public_snapshots("https://example.test/project")
    result = findings(reports, us_report)
    redirected_key = "asia" if redirected_name == "reports.json" else "us"
    other_key = "us" if redirected_key == "asia" else "asia"
    assert result[redirected_key]["status"] == "unavailable"
    assert result[other_key]["status"] == "ok"


def test_redirect_is_rejected_without_requesting_redirect_target(monkeypatch):
    seen = []
    base = "https://example.test/project"
    first = base + "/data/reports.json"
    second = base + "/data/market_daily_report.json"

    class FakeHTTPSHandler(HTTPSHandler):
        def https_open(self, request: Request):
            seen.append(request.full_url)
            headers = Message()
            if request.full_url == first:
                headers["Location"] = "https://other.example.test/private"
                response = addinfourl(io.BytesIO(b"redirect body"), headers, request.full_url, code=302)
                response.msg = "Found"
                return response
            payload = us() if request.full_url == second else {"private": "should never fetch"}
            response = addinfourl(
                io.BytesIO(json.dumps(payload).encode()), headers, request.full_url, code=200
            )
            response.msg = "OK"
            return response

    def fake_build_opener(*handlers):
        return build_opener(FakeHTTPSHandler(), *handlers)

    monkeypatch.setattr(public_site_freshness, "build_opener", fake_build_opener)
    reports, us_report = fetch_public_snapshots(base)
    assert seen == [first, second]
    result = findings(reports, us_report)
    assert result["asia"]["status"] == "unavailable"
    assert result["us"]["status"] == "ok"


@pytest.mark.parametrize("fault", ["network", "oversize", "json", "array"])
def test_fetch_failure_yields_availability_finding_without_exposing_response(monkeypatch, fault):
    secret = "sensitive response content"

    class Response(io.BytesIO):
        def __init__(self, payload, url):
            super().__init__(payload)
            self.url = url

        def geturl(self):
            return self.url

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
            return Response(raw, request.full_url)
        return Response(json.dumps(us()).encode(), request.full_url)

    monkeypatch.setattr(
        public_site_freshness, "build_opener", lambda *handlers: SimpleNamespace(open=open_url)
    )
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


def calendar_findings(day, reports=None, calendar=None, max_age_hours=96):
    from scripts.public_site_calendar import load_calendar

    if calendar is None:
        calendar = load_calendar()
        calendar["generated_at"] = "2026-09-30T00:00:00+00:00"
    return evaluate_public_snapshots(
        asia("2026-09-30", "2026-09-30 20:00:00") if reports is None else reports,
        us(),
        now=datetime.fromisoformat(day),
        calendar=calendar,
        max_age_hours=max_age_hours,
    )[0]


@pytest.mark.parametrize(
    "day",
    [
        "2026-10-04T23:00:00+08:00",
    ],
)
def test_all_asian_markets_closed_defers_existing_alert(day):
    assert (
        calendar_findings(day, asia("2026-10-02", "2026-10-02 20:00:00"), max_age_hours=24)["status"]
        == "deferred"
    )


def test_sse_overdue_session_resumes_alert_and_real_recovery_is_ok():
    day = "2026-10-08T22:00:00+08:00"
    assert calendar_findings(day)["status"] == "review"
    assert calendar_findings(day, asia("2026-10-08", "2026-10-08 20:00:00"))["status"] == "ok"


@pytest.mark.parametrize(
    "reports", [asia(), asia("2026-09-30", "bad"), asia("2026-09-30", "2026-09-29 20:00:00"), {"reports": []}]
)
def test_closure_cannot_mask_behind_or_invalid_snapshot(reports):
    assert calendar_findings("2026-10-05T12:00:00+08:00", reports)["status"] in {"review", "unavailable"}


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "gap",
        "flag",
        "exchange",
        "hash",
        "expired",
        "future",
        "version",
        "references",
        "reference_url",
    ],
)
def test_calendar_invalidity_fails_closed(fault):
    from scripts.public_site_calendar import load_calendar

    calendar = load_calendar()
    now = "2026-10-05T12:00:00+08:00"
    if fault == "missing":
        calendar = {}
    elif fault == "gap":
        del calendar["days"]["2026-10-02"]
    elif fault == "flag":
        calendar["days"]["2026-10-05"] = "closed"
    elif fault == "exchange":
        calendar["exchange"] = "SSE"
    elif fault == "hash":
        calendar["source_sha256"] = "invalid"
    elif fault == "expired":
        now = "2027-01-01T12:00:00+08:00"
    elif fault == "version":
        calendar["exchange_calendars_version"] = "unknown"
    elif fault == "references":
        calendar["exchange_sources"] = {}
    elif fault == "reference_url":
        calendar["exchange_sources"]["HK"]["url"] = "https://untrusted.example/"
    else:
        calendar["generated_at"] = "2027-01-01T00:00:00+00:00"
    assert calendar_findings(now, calendar=calendar)["status"] == "unavailable"


def test_reopening_report_arriving_before_deadline_is_healthy():
    assert (
        calendar_findings("2026-10-08T21:00:00+08:00", asia("2026-10-08", "2026-10-08 20:00:00"))["status"]
        == "ok"
    )


def test_hk_japan_session_is_accepted_during_sse_holiday():
    assert (
        calendar_findings("2026-10-05T20:00:00+08:00", asia("2026-10-05", "2026-10-05 18:00:00"))["status"]
        == "ok"
    )


def test_hk_japan_open_day_requires_current_evening_after_deadline():
    assert calendar_findings("2026-10-05T23:00:00+08:00")["status"] == "review"
    assert (
        calendar_findings("2026-10-05T23:00:00+08:00", asia("2026-10-05", "2026-10-05 20:00:00"))["status"]
        == "ok"
    )


@pytest.mark.parametrize("content", ["not JSON", "[]", None])
def test_calendar_loader_missing_or_unreadable_fails_closed(monkeypatch, tmp_path, content):
    from scripts import public_site_calendar

    path = tmp_path / "calendar.json"
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(public_site_calendar, "CALENDAR_PATH", path)
    assert public_site_calendar.load_calendar() == {}


def test_postholiday_fresh_report_recovers_at_next_overnight_monitor():
    assert (
        calendar_findings("2026-10-09T02:00:00+08:00", asia("2026-10-08", "2026-10-08 20:00:00"))["status"]
        == "ok"
    )


def test_recent_last_session_during_closure_remains_healthy():
    assert calendar_findings("2026-10-01T12:00:00+08:00")["status"] == "ok"
