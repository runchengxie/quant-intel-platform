"""Reconcile public-site findings with one GitHub Issue per alert key."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from .public_site_freshness import evaluate_public_snapshots, fetch_public_snapshots
except ImportError:
    from public_site_freshness import evaluate_public_snapshots, fetch_public_snapshots

LABEL = "public-site-alert"
_EVENT_RE = re.compile(r"(?m)^event_id: ([0-9]+)$")
_MAX_FINDING = 400
PAGES_BASE = "https://runchengxie.github.io/quant-intel-platform"


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        raise RuntimeError("GitHub API redirect rejected")


def _api_open(request: Request, timeout: int):
    return build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


class IssueClient:
    """Minimal GitHub Issues REST client for the trusted monitoring workflow."""

    def __init__(self, token: str, repository: str) -> None:
        parts = repository.split("/")
        if not token or len(parts) != 2 or not all(parts):
            raise ValueError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
        self._token = token
        self._repository = repository
        self._base = "https://api.github.com/repos/" + "/".join(quote(part, safe="") for part in parts)

    @classmethod
    def from_environment(cls) -> IssueClient:
        return cls(os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", ""))

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        request = Request(
            self._base + path,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with _api_open(request, timeout=10) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"GitHub Issues API returned HTTP {error.code}") from None
        except OSError:
            raise RuntimeError("GitHub Issues API request failed") from None
        except (ValueError, UnicodeError):
            raise RuntimeError("GitHub Issues API returned invalid JSON") from None

    def _list_pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            response = self._request("GET", f"{path}{separator}{urlencode({'per_page': 100, 'page': page})}")
            if not isinstance(response, list) or any(not isinstance(item, dict) for item in response):
                raise RuntimeError("GitHub Issues API returned invalid issue data")
            items.extend(response)
            if len(response) < 100:
                return items
            page += 1

    def list_issues(self) -> list[dict[str, Any]]:
        return self._list_pages(f"/issues?{urlencode({'state': 'all', 'labels': LABEL})}")

    def list_comments(self, number: int) -> list[dict[str, Any]]:
        return self._list_pages(f"/issues/{number}/comments")

    def latest_workflow_run(self, branch: str) -> dict[str, Any] | None:
        """Read the latest completed Public website run for the exact branch."""
        matching: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urlencode({"branch": branch, "status": "completed", "per_page": 100, "page": page})
            response = self._request("GET", f"/actions/workflows/public-site.yml/runs?{query}")
            if not isinstance(response, dict) or not isinstance(response.get("workflow_runs"), list):
                raise RuntimeError("GitHub Actions API returned invalid run data")
            runs = response["workflow_runs"]
            for run in runs:
                if not isinstance(run, dict) or run.get("head_branch") != branch:
                    continue
                repository = run.get("head_repository")
                if not isinstance(repository, dict) or not isinstance(repository.get("full_name"), str):
                    raise RuntimeError("GitHub Actions API returned incomplete repository data")
                if (
                    repository["full_name"] == self._repository
                    and run.get("status") == "completed"
                    and isinstance(run.get("id"), int)
                ):
                    matching.append(run)
            if len(runs) < 100:
                break
            page += 1
        if not matching:
            return None
        return max(matching, key=lambda run: run["id"])

    def create_issue(self, *, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        response = self._request("POST", "/issues", {"title": title, "body": body, "labels": labels})
        if not isinstance(response, dict):
            raise RuntimeError("GitHub Issues API returned invalid issue data")
        return response

    def comment_issue(self, number: int, body: str) -> None:
        self._request("POST", f"/issues/{number}/comments", {"body": body})

    def close_issue(self, number: int) -> None:
        self._request("PATCH", f"/issues/{number}", {"state": "closed"})


def _event_id(body: object) -> int:
    match = _EVENT_RE.search(body) if isinstance(body, str) else None
    return int(match.group(1)) if match else -1


def _message(marker: str, event_id: int, run_url: str, finding: str | None) -> str:
    status = "Recovered" if finding is None else "Review public site alert"
    lines = [marker, f"event_id: {event_id}", status, f"Run: {run_url}"]
    if finding is not None:
        summary = " ".join(finding.split())[:_MAX_FINDING]
        lines.append(f"Finding: {summary}")
    return "\n".join(lines)


def _latest_issue(client: IssueClient, marker: str) -> tuple[dict[str, Any] | None, int]:
    latest_issue: dict[str, Any] | None = None
    latest_event = -1
    for issue in client.list_issues():
        labels = issue.get("labels", [])
        if (
            marker not in str(issue.get("title", ""))
            or LABEL not in [label.get("name") for label in labels if isinstance(label, dict)]
            or "pull_request" in issue
        ):
            continue
        number = issue.get("number")
        if not isinstance(number, int):
            raise RuntimeError("GitHub Issues API returned invalid issue data")
        recorded = max(
            [_event_id(issue.get("body"))]
            + [
                _event_id(comment.get("body"))
                for comment in client.list_comments(number)
                if marker in str(comment.get("body", "")).splitlines()
            ]
        )
        if recorded >= latest_event:
            latest_issue, latest_event = issue, recorded
    return latest_issue, latest_event


def reconcile_alert(
    client: IssueClient, *, key: str, finding: str | None, run_url: str, event_id: int
) -> str:
    """Create, comment on, or close an alert; ignore events older than recorded state."""
    if not key or event_id < 0:
        raise ValueError("alert key and nonnegative event_id are required")
    url = urlsplit(run_url)
    if (
        url.scheme != "https"
        or url.hostname != "github.com"
        or url.username
        or url.password
        or url.query
        or url.fragment
        or re.fullmatch(r"/[^/]+/[^/]+/actions/runs/[0-9]+", url.path) is None
    ):
        raise ValueError("run_url must be a GitHub HTTPS URL")
    marker = f"[public-site-alert:{quote(key, safe=':/-_.')}]"
    latest_issue, latest_event = _latest_issue(client, marker)
    if event_id < latest_event or (event_id == latest_event and finding is not None):
        return "unchanged"
    if finding is None:
        if latest_issue is None or latest_issue.get("state") != "open":
            return "unchanged"
        number = latest_issue["number"]
        if event_id > latest_event:
            client.comment_issue(number, _message(marker, event_id, run_url, None))
        client.close_issue(number)
        return "closed"
    body = _message(marker, event_id, run_url, finding)
    if latest_issue is not None and latest_issue.get("state") == "open":
        client.comment_issue(latest_issue["number"], body)
        return "commented"
    client.create_issue(title=f"Public site alert {marker}", body=body, labels=[LABEL])
    return "created"


def _run_url(repository: str, run_id: int) -> str:
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None or run_id <= 0:
        raise ValueError("valid GITHUB_REPOSITORY and run ID are required")
    return f"https://github.com/{repository}/actions/runs/{run_id}"


def _branch_allowed(branch: object) -> bool:
    return isinstance(branch, str) and (
        branch == "main"
        or (branch.startswith("automation/pages-") and len(branch) > len("automation/pages-"))
    )


def _alert(
    client: IssueClient, *, key: str, finding: str | None, repository: str, run_id: int, dry_run: bool
) -> str:
    url = _run_url(repository, run_id)
    if dry_run:
        return "would-create" if finding is not None else "would-close"
    return reconcile_alert(client, key=key, finding=finding, run_url=url, event_id=run_id)


def process_workflow_event(
    client: IssueClient, event: dict[str, Any], *, repository: str, dry_run: bool = False
) -> str:
    """Reconcile only completed, eligible Public website runs."""
    run = event.get("workflow_run")
    if not isinstance(run, dict) or event.get("action") != "completed":
        return "ignored"
    branch = run.get("head_branch")
    if (
        run.get("name") != "Public website"
        or not _branch_allowed(branch)
        or run.get("status") != "completed"
        or run.get("conclusion") not in {"success", "failure"}
    ):
        return "ignored"
    head_repository = run.get("head_repository")
    if not isinstance(head_repository, dict) or head_repository.get("full_name") != repository:
        return "ignored"
    run_id = run.get("id")
    if not isinstance(run_id, int) or run_id <= 0:
        raise ValueError("workflow_run.id must be positive")
    latest = None if dry_run else client.latest_workflow_run(branch)
    if latest is not None and latest["id"] > run_id:
        if latest.get("conclusion") not in {"success", "failure"}:
            return "ignored"
        run = latest
        run_id = latest["id"]
    finding = (
        "Public website build failed; review the linked Actions run."
        if run["conclusion"] == "failure"
        else None
    )
    return _alert(
        client, key=f"build:{branch}", finding=finding, repository=repository, run_id=run_id, dry_run=dry_run
    )


def process_freshness_event(
    client: IssueClient, *, repository: str, run_id: int, dry_run: bool = False
) -> list[str]:
    """Evaluate live public snapshots and reconcile each independent stream."""
    reports, us_report = fetch_public_snapshots(PAGES_BASE)
    findings = evaluate_public_snapshots(reports, us_report, now=datetime.now(UTC))
    return [
        _alert(
            client,
            key=f"freshness:{item['key']}",
            finding=item["summary"] if item["status"] != "ok" else None,
            repository=repository,
            run_id=run_id,
            dry_run=dry_run,
        )
        for item in findings
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor public site publication and freshness")
    parser.add_argument("--mode", required=True, choices=("freshness", "workflow"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise ValueError("GITHUB_EVENT_PATH is required")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if not isinstance(event, dict):
        raise ValueError("GitHub event must be a JSON object")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = int(os.environ.get("GITHUB_RUN_ID", "0"))
    client = IssueClient("dry-run-token", repository) if args.dry_run else IssueClient.from_environment()
    if args.mode == "workflow":
        result = process_workflow_event(client, event, repository=repository, dry_run=args.dry_run)
        print(f"Workflow monitor: {result}")
    else:
        results = process_freshness_event(client, repository=repository, run_id=run_id, dry_run=args.dry_run)
        print("Freshness monitor: " + ", ".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
