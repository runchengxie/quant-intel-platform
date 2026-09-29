"""Reconcile public-site findings with one GitHub Issue per alert key."""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

LABEL = "public-site-alert"
_EVENT_RE = re.compile(r"(?m)^event_id: ([0-9]+)$")
_MAX_FINDING = 400


class IssueClient:
    """Minimal GitHub Issues REST client for the trusted monitoring workflow."""

    def __init__(self, token: str, repository: str) -> None:
        parts = repository.split("/")
        if not token or len(parts) != 2 or not all(parts):
            raise ValueError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
        self._token = token
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
            with urlopen(request, timeout=10) as response:
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
