#!/usr/bin/env python3
"""Delete feature branches only after GitHub confirms a merged pull request."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence

ALLOWED_PREFIXES = ("feat/", "fix/", "hotfix/", "chore/", "release/")
CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def validate_branch_name(branch: str) -> str:
    if not branch or branch in {"main", "HEAD"} or branch.startswith("refs/"):
        raise ValueError(f"branch is not eligible for cleanup: {branch!r}")
    if not branch.startswith(ALLOWED_PREFIXES):
        raise ValueError(f"branch is not in an allowed cleanup namespace: {branch!r}")
    return branch


def parse_merged_prs(payload: str, *, repo: str, branch: str, head_oid: str) -> tuple[int, ...]:
    try:
        records = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("gh returned invalid pull-request JSON") from exc
    if not isinstance(records, list):
        raise ValueError("gh returned an invalid pull-request list")
    numbers: list[int] = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("number"), int):
            raise ValueError("gh returned an invalid pull-request record")
        head_repository = record.get("headRepository")
        if (
            record.get("mergedAt")
            and record.get("headRefName") == branch
            and record.get("headRefOid") == head_oid
            and isinstance(head_repository, dict)
            and head_repository.get("nameWithOwner") == repo
        ):
            numbers.append(record["number"])
    if not numbers:
        raise ValueError("no merged PR was found for this branch")
    return tuple(numbers)


def github_repo(remote_url: str) -> str:
    normalized = remote_url.removesuffix(".git").rstrip("/")
    if normalized.startswith("git@github.com:"):
        return normalized.removeprefix("git@github.com:")
    prefix = "https://github.com/"
    if normalized.startswith(prefix):
        return normalized.removeprefix(prefix)
    raise ValueError(f"remote is not a GitHub repository: {remote_url}")


def remote_repository(remote: str, *, runner: CommandRunner) -> str:
    result = runner(("git", "remote", "get-url", remote))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"cannot resolve remote {remote!r}")
    return github_repo(result.stdout.strip())


def remote_branch_oid(remote: str, branch: str, *, runner: CommandRunner) -> str:
    result = runner(("git", "ls-remote", "--heads", remote, branch))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "cannot resolve remote branch")
    lines = result.stdout.strip().splitlines()
    if not lines:
        raise ValueError(f"remote branch does not exist: {remote}/{branch}")
    return lines[0].split()[0]


def merged_pr_numbers(
    repo: str,
    branch: str,
    *,
    head_oid: str,
    runner: CommandRunner = lambda command: subprocess.run(
        command, capture_output=True, text=True, check=False
    ),
) -> tuple[int, ...]:
    result = runner(
        (
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--head",
            branch,
            "--json",
            "number,mergedAt,headRefName,headRefOid,headRepository",
        )
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "gh pr list failed"
        raise RuntimeError(detail)
    return parse_merged_prs(result.stdout, repo=repo, branch=branch, head_oid=head_oid)


def cleanup_branch(
    remote: str,
    branch: str,
    *,
    repo: str,
    dry_run: bool,
    yes: bool,
    runner: CommandRunner = lambda command: subprocess.run(
        command, capture_output=True, text=True, check=False
    ),
) -> tuple[int, ...]:
    validate_branch_name(branch)
    if remote_repository(remote, runner=runner) != repo:
        raise ValueError(f"remote {remote!r} does not point to GitHub repository {repo!r}")
    head_oid = remote_branch_oid(remote, branch, runner=runner)
    numbers = merged_pr_numbers(repo, branch, head_oid=head_oid, runner=runner)
    if dry_run:
        print(f"would delete {remote}/{branch} after merged PR(s): {', '.join(map(str, numbers))}")
        return numbers
    if not yes:
        raise ValueError("refusing deletion without --yes")
    result = runner(("git", "push", remote, "--delete", branch))
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "git branch deletion failed"
        )
    return numbers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", action="append", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="confirm remote deletion")
    args = parser.parse_args(argv)
    try:
        for branch in args.branch:
            cleanup_branch(args.remote, branch, repo=args.repo, dry_run=args.dry_run, yes=args.yes)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
