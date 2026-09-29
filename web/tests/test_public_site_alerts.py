"""Issue reconciliation tests use an in-memory API, never GitHub."""

from __future__ import annotations

import io
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from scripts.public_site_alerts import IssueClient, reconcile_alert


class FakeIssues:
    def __init__(self) -> None:
        self.issues: list[dict[str, Any]] = []
        self.comments: list[tuple[int, str]] = []
        self.closed: list[int] = []

    def list_issues(self) -> list[dict[str, Any]]:
        return self.issues

    def create_issue(self, *, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        issue = {
            "number": len(self.issues) + 1,
            "title": title,
            "body": body,
            "labels": [{"name": label} for label in labels],
            "state": "open",
        }
        self.issues.append(issue)
        return issue

    def comment_issue(self, number: int, body: str) -> None:
        self.comments.append((number, body))

    def list_comments(self, number: int) -> list[dict[str, str]]:
        return [{"body": body} for issue_number, body in self.comments if issue_number == number]

    def close_issue(self, number: int) -> None:
        self.closed.append(number)
        self.issues[number - 1]["state"] = "closed"


RUN_URL = "https://github.com/example/site/actions/runs/123"


def test_first_failure_creates_one_labeled_issue_with_marker_and_event() -> None:
    client = FakeIssues()

    result = reconcile_alert(client, key="build:main", finding="Build failed", run_url=RUN_URL, event_id=100)

    assert result == "created"
    assert len(client.issues) == 1
    issue = client.issues[0]
    assert issue["labels"] == [{"name": "public-site-alert"}]
    assert "[public-site-alert:build:main]" in issue["body"]
    assert "event_id: 100" in issue["body"]
    assert "Build failed" in issue["body"]
    assert RUN_URL in issue["body"]


def test_new_failure_comments_on_existing_issue_and_duplicate_event_does_nothing() -> None:
    client = FakeIssues()
    reconcile_alert(client, key="build:main", finding="Build failed", run_url=RUN_URL, event_id=100)

    assert (
        reconcile_alert(client, key="build:main", finding="Build failed again", run_url=RUN_URL, event_id=101)
        == "commented"
    )
    assert (
        reconcile_alert(client, key="build:main", finding="Duplicate", run_url=RUN_URL, event_id=101)
        == "unchanged"
    )
    assert len(client.issues) == 1
    assert len(client.comments) == 1
    assert client.comments[0][0] == 1
    assert "event_id: 101" in client.comments[0][1]


def test_recovery_closes_only_matching_open_issue() -> None:
    client = FakeIssues()
    reconcile_alert(client, key="build:main", finding="Main failed", run_url=RUN_URL, event_id=100)
    reconcile_alert(
        client, key="build:automation/pages-daily", finding="Daily failed", run_url=RUN_URL, event_id=101
    )

    assert reconcile_alert(client, key="build:main", finding=None, run_url=RUN_URL, event_id=102) == "closed"
    assert [issue["state"] for issue in client.issues] == ["closed", "open"]
    assert client.closed == [1]


def test_old_event_cannot_close_newer_failure_or_reopen_newer_recovery() -> None:
    client = FakeIssues()
    reconcile_alert(client, key="build:main", finding="Failed", run_url=RUN_URL, event_id=200)
    assert (
        reconcile_alert(client, key="build:main", finding=None, run_url=RUN_URL, event_id=199) == "unchanged"
    )
    assert client.issues[0]["state"] == "open"

    reconcile_alert(client, key="build:main", finding=None, run_url=RUN_URL, event_id=201)
    assert (
        reconcile_alert(client, key="build:main", finding="Old failure", run_url=RUN_URL, event_id=200)
        == "unchanged"
    )
    assert len(client.issues) == 1
    assert client.issues[0]["state"] == "closed"


def test_api_error_propagates() -> None:
    class FailingIssues(FakeIssues):
        def list_issues(self) -> list[dict[str, Any]]:
            raise RuntimeError("GitHub API unavailable")

    with pytest.raises(RuntimeError, match="GitHub API unavailable"):
        reconcile_alert(FailingIssues(), key="build:main", finding="Failed", run_url=RUN_URL, event_id=1)


def test_marker_encodes_untrusted_key_and_diagnostic_is_bounded() -> None:
    client = FakeIssues()
    unsafe_key = "build:branch] injected\n"
    reconcile_alert(client, key=unsafe_key, finding="X" * 10_000, run_url=RUN_URL, event_id=1)

    body = client.issues[0]["body"]
    assert "[public-site-alert:build:branch%5D%20injected%0A]" in body
    assert len(body) < 1_000
    assert "X" * 1_000 not in body


def test_client_encodes_repository_and_query_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
        urls.append(request.full_url)
        assert timeout == 10
        return io.BytesIO(b"[]")

    monkeypatch.setattr("scripts.public_site_alerts.urlopen", fake_urlopen)
    assert IssueClient("secret", "owner name/repo name").list_issues() == []
    assert urls == [
        "https://api.github.com/repos/owner%20name/repo%20name/issues?state=all&labels=public-site-alert&per_page=100&page=1"
    ]
    assert "secret" not in urls[0]


def test_client_http_error_omits_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
        raise HTTPError(request.full_url, 403, "private diagnostics", {}, io.BytesIO(b"secret report body"))

    monkeypatch.setattr("scripts.public_site_alerts.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="GitHub Issues API returned HTTP 403") as error:
        IssueClient("secret", "example/site").list_issues()
    assert "secret report body" not in str(error.value)
    assert "private diagnostics" not in str(error.value)


def test_client_transport_error_omits_sensitive_details(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
        raise OSError("private request detail")

    monkeypatch.setattr("scripts.public_site_alerts.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="GitHub Issues API request failed") as error:
        IssueClient("secret", "example/site").list_issues()
    assert "private request detail" not in str(error.value)


def test_run_url_cannot_carry_untrusted_query_into_issue() -> None:
    with pytest.raises(ValueError, match="run_url"):
        reconcile_alert(
            FakeIssues(),
            key="build:main",
            finding="Failed",
            run_url=RUN_URL + "?token=private",
            event_id=1,
        )
