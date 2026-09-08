#!/usr/bin/env python3
"""Run market-intel's local quality gate before a Git push."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
REMOTE_QUALITY_PATTERN = re.compile(
    r"(?:"
    r"\b(?:pytest|ruff|shellcheck|shfmt|mypy|pyright|basedpyright|pylint|flake8|tox|nox)\b"
    r"|\bty\s+check\b"
    r"|\b(?:uv|python\s+-m)\s+build\b"
    r"|\buv\s+lock\s+--check\b"
    r"|\bbash\s+-n\b"
    r"|\bnode\s+--check\b"
    r"|PSScriptAnalyzer|Invoke-ScriptAnalyzer"
    r"|project_tools/(?:check_all|update_cli_help)\.py"
    r"|scripts/dev/(?:check|maintainability_metrics)\.py"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PushUpdate:
    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str

    @property
    def deletes_ref(self) -> bool:
        return self.local_ref == "(delete)" or bool(
            self.local_sha and not self.local_sha.strip("0")
        )


def _is_truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in TRUE_VALUES)


def parse_push_updates(payload: str) -> tuple[PushUpdate, ...]:
    updates: list[PushUpdate] = []
    for line_number, raw_line in enumerate(payload.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f"Malformed pre-push input on line {line_number}: expected 4 fields")
        updates.append(PushUpdate(*fields))
    return tuple(updates)


ALLOWED_BRANCH_PREFIXES = (
    "refs/heads/feat/",
    "refs/heads/fix/",
    "refs/heads/hotfix/",
    "refs/heads/chore/",
    "refs/heads/release/",
)


def validate_push_destinations(updates: Sequence[PushUpdate]) -> None:
    for update in updates:
        if update.remote_ref.startswith("refs/heads/"):
            if any(update.remote_ref.startswith(prefix) for prefix in ALLOWED_BRANCH_PREFIXES):
                continue
            if update.remote_ref == "refs/heads/main":
                if update.deletes_ref:
                    raise ValueError("deleting remote main is forbidden")
                continue
            raise ValueError(
                f"{update.remote_ref}: only refs/heads/main or "
                "refs/heads/{feat,fix,hotfix,release}/* are allowed"
            )
        if update.remote_ref.startswith("refs/tags/"):
            if update.deletes_ref:
                raise ValueError(f"{update.remote_ref}: deleting remote tags is forbidden")
            continue
        raise ValueError(f"{update.remote_ref}: only remote main and tags are allowed")


def project_for_repository(repository: Path, *, root: Path = ROOT) -> str:
    """Only market-intel itself is managed by this hook."""
    if repository.resolve() == root.resolve():
        return "root"
    raise ValueError(f"Unsupported repository for market-intel pre-push hook: {repository}")


def command_for_push(project: str, updates: Sequence[PushUpdate]) -> tuple[str, ...] | None:
    if project != "root":
        raise ValueError(f"Unsupported project for market-intel quality gate: {project}")
    content_updates = tuple(update for update in updates if not update.deletes_ref)
    if not content_updates:
        return None
    pushes_release = any(
        update.remote_ref == "refs/heads/main" or update.remote_ref.startswith("refs/tags/")
        for update in content_updates
    )
    command = (
        "uv",
        "run",
        "python",
        "project_tools/check_all.py",
        "--project",
        "root",
    )
    if pushes_release:
        return ("uv", "run", "python", "project_tools/check_all.py", "--scope", "all")
    return (*command, "--include-non-python")


def _git_output(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return completed.stdout.strip()


def validate_push_state(repository: Path, updates: Sequence[PushUpdate]) -> None:
    content_updates = tuple(update for update in updates if not update.deletes_ref)
    if not content_updates:
        return
    status = _git_output(
        repository,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    if status:
        raise ValueError(
            "repository is not clean; commit or stash all changes before pushing so checks "
            "match the pushed commit"
        )
    head = _git_output(repository, "rev-parse", "HEAD")
    for update in content_updates:
        pushed_commit = _git_output(repository, "rev-parse", f"{update.local_sha}^{{commit}}")
        if pushed_commit != head:
            raise ValueError(
                "pushed ref does not resolve to the checked-out HEAD; checkout that commit "
                "and push it separately"
            )


def remote_quality_workflows(repository: Path) -> tuple[Path, ...]:
    workflow_root = repository / ".github" / "workflows"
    if not workflow_root.is_dir():
        return ()
    matches: list[Path] = []
    for pattern in ("*.yml", "*.yaml"):
        for path in workflow_root.glob(pattern):
            if path.is_file() and REMOTE_QUALITY_PATTERN.search(
                path.read_text(encoding="utf-8", errors="replace")
            ):
                matches.append(path.relative_to(repository))
    return tuple(sorted(set(matches)))


def validate_local_only_quality_policy(
    *,
    project: str,
    repository: Path,
    root: Path,
) -> None:
    del root
    if project != "root":
        raise ValueError(f"Unsupported project for market-intel quality policy: {project}")
    violations = [
        f"{repository.name}/{path.as_posix()}" for path in remote_quality_workflows(repository)
    ]
    if violations:
        joined = ", ".join(violations)
        raise ValueError(
            "GitHub workflow duplicates local code-quality checks and may consume Actions "
            f"minutes: {joined}"
        )


def _display_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def run_guard(
    *,
    repository: Path,
    payload: str,
    environ: Mapping[str, str] = os.environ,
    root: Path = ROOT,
) -> int:
    project = project_for_repository(repository, root=root)
    updates = parse_push_updates(payload)
    validate_push_destinations(updates)
    if _is_truthy(environ.get("SKIP_LOCAL_CHECKS")):
        print(
            f"[pre-push] WARNING: skipping local checks for {project} "
            "because SKIP_LOCAL_CHECKS is enabled.",
            file=sys.stderr,
        )
        return 0

    command = command_for_push(project, updates)
    if command is None:
        print(f"[pre-push] {project}: no content refs to push; no checks required.")
        return 0

    validate_local_only_quality_policy(project=project, repository=repository, root=root)
    validate_push_state(repository, updates)
    print(f"[pre-push] {project}: {_display_command(command)}", flush=True)
    if _is_truthy(environ.get("MARKET_INTEL_PRE_PUSH_DRY_RUN")):
        print("[pre-push] dry-run; command not executed.")
        return 0
    completed = subprocess.run(command, cwd=root, check=False)
    validate_push_state(repository, updates)
    if completed.returncode != 0:
        print(
            f"[pre-push] {project}: local quality gate failed; push blocked.",
            file=sys.stderr,
        )
    return completed.returncode


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--remote-name", default="")
    parser.add_argument("--remote-location", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    del args.remote_name, args.remote_location
    try:
        return run_guard(repository=args.repository, payload=sys.stdin.read())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[pre-push] FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
