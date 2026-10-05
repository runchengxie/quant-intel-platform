"""Issue reconciliation tests use an in-memory API, never GitHub."""

from __future__ import annotations

import io
import json
from pathlib import Path
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
        self.latest: dict[str, Any] | None = None

    def latest_workflow_run(self, branch: str) -> dict[str, Any] | None:
        assert branch in {"main", "automation/pages-daily"}
        return self.latest

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


def test_human_comment_event_id_cannot_block_reconciler_update() -> None:
    client = FakeIssues()
    reconcile_alert(client, key="build:main", finding="Failed", run_url=RUN_URL, event_id=100)
    client.comments.extend(
        [
            (1, "event_id: 9999999\nHuman triage note"),
            (1, "[public-site-alert:build:other]\nevent_id: 9999999"),
        ]
    )

    assert (
        reconcile_alert(client, key="build:main", finding="Still failed", run_url=RUN_URL, event_id=101)
        == "commented"
    )
    assert len(client.comments) == 3
    assert "event_id: 101" in client.comments[-1][1]


def test_recovery_retry_finishes_close_after_comment_succeeded() -> None:
    class FailFirstClose(FakeIssues):
        def __init__(self) -> None:
            super().__init__()
            self.fail_next_close = True

        def close_issue(self, number: int) -> None:
            if self.fail_next_close:
                self.fail_next_close = False
                raise RuntimeError("GitHub API unavailable")
            super().close_issue(number)

    client = FailFirstClose()
    reconcile_alert(client, key="build:main", finding="Failed", run_url=RUN_URL, event_id=100)
    with pytest.raises(RuntimeError, match="GitHub API unavailable"):
        reconcile_alert(client, key="build:main", finding=None, run_url=RUN_URL, event_id=101)
    assert client.issues[0]["state"] == "open"
    assert len(client.comments) == 1

    assert reconcile_alert(client, key="build:main", finding=None, run_url=RUN_URL, event_id=101) == "closed"
    assert client.issues[0]["state"] == "closed"
    assert len(client.comments) == 1


def test_new_failure_after_closure_creates_new_issue() -> None:
    client = FakeIssues()
    reconcile_alert(client, key="build:main", finding="Failed", run_url=RUN_URL, event_id=100)
    reconcile_alert(client, key="build:main", finding=None, run_url=RUN_URL, event_id=101)

    assert (
        reconcile_alert(client, key="build:main", finding="Failed again", run_url=RUN_URL, event_id=102)
        == "created"
    )
    assert [issue["state"] for issue in client.issues] == ["closed", "open"]
    assert "event_id: 102" in client.issues[1]["body"]
    assert (
        reconcile_alert(client, key="build:main", finding="Delayed", run_url=RUN_URL, event_id=100)
        == "unchanged"
    )
    assert len(client.issues) == 2


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

    monkeypatch.setattr("scripts.public_site_alerts._api_open", fake_urlopen)
    assert IssueClient("secret", "owner name/repo name").list_issues() == []
    assert urls == [
        "https://api.github.com/repos/owner%20name/repo%20name/issues?state=all&labels=public-site-alert&per_page=100&page=1"
    ]
    assert "secret" not in urls[0]


def test_client_http_error_omits_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
        raise HTTPError(request.full_url, 403, "private diagnostics", {}, io.BytesIO(b"secret report body"))

    monkeypatch.setattr("scripts.public_site_alerts._api_open", fake_urlopen)
    with pytest.raises(RuntimeError, match="GitHub Issues API returned HTTP 403") as error:
        IssueClient("secret", "example/site").list_issues()
    assert "secret report body" not in str(error.value)
    assert "private diagnostics" not in str(error.value)


def test_client_transport_error_omits_sensitive_details(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
        raise OSError("private request detail")

    monkeypatch.setattr("scripts.public_site_alerts._api_open", fake_urlopen)
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


def _workflow_event(branch: str = "main", conclusion: str = "failure", run_id: int = 123) -> dict[str, Any]:
    return {
        "action": "completed",
        "workflow_run": {
            "id": run_id,
            "name": "Public website",
            "head_branch": branch,
            "head_repository": {"full_name": "example/site"},
            "status": "completed",
            "conclusion": conclusion,
        },
    }


def test_workflow_event_filters_unrelated_workflows_branches_and_incomplete_runs() -> None:
    from scripts.public_site_alerts import process_workflow_event

    client = FakeIssues()
    events = [_workflow_event("feature/random"), _workflow_event()]
    events[1]["workflow_run"]["name"] = "Other workflow"
    events.append(_workflow_event())
    events[2]["workflow_run"]["status"] = "in_progress"
    for event in events:
        assert process_workflow_event(client, event, repository="example/site") == "ignored"
    assert client.issues == []


def test_workflow_event_rejects_missing_or_malformed_head_repository() -> None:
    from scripts.public_site_alerts import process_workflow_event

    client = FakeIssues()
    for head_repository in (None, "example/site", {"full_name": "other/fork"}):
        event = _workflow_event()
        event["workflow_run"]["head_repository"] = head_repository
        assert process_workflow_event(client, event, repository="example/site") == "ignored"
    assert client.issues == []


def test_failed_build_alert_and_same_branch_success_closure() -> None:
    from scripts.public_site_alerts import process_workflow_event

    client = FakeIssues()
    assert (
        process_workflow_event(client, _workflow_event("automation/pages-daily"), repository="example/site")
        == "created"
    )
    assert "build:automation/pages-daily" in client.issues[0]["body"]
    assert (
        process_workflow_event(
            client, _workflow_event("automation/pages-daily", "success", 124), repository="example/site"
        )
        == "closed"
    )
    assert client.issues[0]["state"] == "closed"


def test_delayed_failure_after_newer_success_does_not_reopen_issue() -> None:
    from scripts.public_site_alerts import process_workflow_event

    client = FakeIssues()
    client.latest = {"id": 200, "head_branch": "main", "status": "completed", "conclusion": "success"}
    assert (
        process_workflow_event(client, _workflow_event(run_id=100), repository="example/site") == "unchanged"
    )
    assert client.issues == []


def test_latest_run_lookup_uses_exact_branch_and_completed_state(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
        urls.append(request.full_url)
        payload = {
            "workflow_runs": [
                {
                    "id": 203,
                    "head_branch": "main",
                    "head_repository": {"full_name": "other/fork"},
                    "status": "completed",
                    "conclusion": "failure",
                },
                {
                    "id": 202,
                    "head_branch": "other",
                    "head_repository": {"full_name": "example/site"},
                    "status": "completed",
                    "conclusion": "failure",
                },
                {
                    "id": 201,
                    "head_branch": "main",
                    "head_repository": {"full_name": "example/site"},
                    "status": "in_progress",
                    "conclusion": None,
                },
                {
                    "id": 200,
                    "head_branch": "main",
                    "head_repository": {"full_name": "example/site"},
                    "status": "completed",
                    "conclusion": "success",
                },
            ]
        }
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("scripts.public_site_alerts._api_open", fake_urlopen)
    assert IssueClient("secret", "example/site").latest_workflow_run("main")["id"] == 200
    assert urls == [
        "https://api.github.com/repos/example/site/actions/workflows/public-site.yml/runs?"
        "branch=main&status=completed&per_page=100&page=1"
    ]


def test_latest_run_lookup_fails_closed_on_incomplete_paginated_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_api_open(request: Request, timeout: int) -> io.BytesIO:
        if request.full_url.endswith("page=1"):
            runs = [
                {
                    "id": index,
                    "head_branch": "other",
                    "head_repository": {"full_name": "example/site"},
                    "status": "completed",
                }
                for index in range(100)
            ]
        else:
            runs = [{"id": 999, "head_branch": "main", "status": "completed"}]
        return io.BytesIO(json.dumps({"workflow_runs": runs}).encode("utf-8"))

    monkeypatch.setattr("scripts.public_site_alerts._api_open", fake_api_open)
    with pytest.raises(RuntimeError, match="incomplete repository"):
        IssueClient("secret", "example/site").latest_workflow_run("main")


def test_api_client_rejects_redirect_without_forwarding_token() -> None:
    from scripts.public_site_alerts import _NoRedirectHandler

    with pytest.raises(RuntimeError, match="redirect rejected"):
        _NoRedirectHandler().redirect_request(None, None, 302, "found", {}, "https://evil.test")


def test_freshness_reconciles_stale_and_healthy_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.public_site_alerts import process_freshness_event

    client = FakeIssues()
    findings = [
        {"key": "asia", "status": "review", "summary": "Review Asian report freshness."},
        {"key": "us", "status": "ok", "summary": "U.S. report healthy."},
    ]
    monkeypatch.setattr("scripts.public_site_alerts.fetch_public_snapshots", lambda base_url: ({}, {}))
    monkeypatch.setattr(
        "scripts.public_site_alerts.evaluate_public_snapshots", lambda reports, us, now, **kwargs: findings
    )
    assert process_freshness_event(client, repository="example/site", run_id=123) == ["created", "unchanged"]
    findings[0] = {"key": "asia", "status": "ok", "summary": "Asian report healthy."}
    assert process_freshness_event(client, repository="example/site", run_id=124) == ["closed", "unchanged"]
    assert client.issues[0]["state"] == "closed"


def test_dry_run_issues_no_write_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.public_site_alerts import process_freshness_event, process_workflow_event

    client = FakeIssues()
    monkeypatch.setattr("scripts.public_site_alerts.fetch_public_snapshots", lambda base_url: ({}, {}))
    monkeypatch.setattr(
        "scripts.public_site_alerts.evaluate_public_snapshots",
        lambda reports, us, now, **kwargs: [
            {"key": "asia", "status": "review", "summary": "Review freshness."}
        ],
    )
    assert process_freshness_event(client, repository="example/site", run_id=123, dry_run=True) == [
        "would-create"
    ]
    assert (
        process_workflow_event(client, _workflow_event(), repository="example/site", dry_run=True)
        == "would-create"
    )
    assert client.issues == [] and client.comments == [] and client.closed == []


def test_cli_reads_event_path_and_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from scripts.public_site_alerts import main

    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(_workflow_event()), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/site")
    monkeypatch.setenv("GITHUB_RUN_ID", "321")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert main(["--mode", "workflow", "--dry-run"]) == 0


def test_workflow_has_trusted_checkout_and_global_issue_write_serialization() -> None:
    workflow = Path(__file__).parents[2] / ".github/workflows/public-site-monitor.yml"
    source = workflow.read_text(encoding="utf-8")
    assert "workflow_run:\n    workflows: [Public website]\n    types: [completed]" in source
    assert "cron: '0 */6 * * *'" in source
    assert "group: public-site-monitor-issues\n  cancel-in-progress: false" in source
    assert "  monitor:\n" in source
    assert "      issues: write\n" in source
    assert "      actions: read\n" in source
    assert source.count("ref: main") == 2
    assert "${{ github.event.workflow_run" not in source
    assert "if: inputs.dry_run == false" in source
    assert "Only dry-run workflow_dispatch is supported" in source


def test_calendar_deferral_preserves_open_issue_without_comments(monkeypatch):
    from scripts.public_site_alerts import process_freshness_event

    client = FakeIssues()
    reconcile_alert(
        client, key="freshness:asia", finding="Existing stale alert", run_url=RUN_URL, event_id=100
    )
    monkeypatch.setattr("scripts.public_site_alerts.fetch_public_snapshots", lambda base_url: ({}, {}))
    monkeypatch.setattr(
        "scripts.public_site_alerts.evaluate_public_snapshots",
        lambda *args, **kwargs: [{"key": "asia", "status": "deferred", "summary": "SSE closure"}],
    )
    assert process_freshness_event(client, repository="example/site", run_id=101) == ["deferred"]
    assert client.issues[0]["state"] == "open"
    assert client.comments == [] and client.closed == []
