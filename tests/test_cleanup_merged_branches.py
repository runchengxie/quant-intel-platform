from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cleanup_merged_branches", ROOT / "project_tools/cleanup_merged_branches.py"
)
assert SPEC is not None and SPEC.loader is not None
cleanup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cleanup
SPEC.loader.exec_module(cleanup)


@pytest.mark.parametrize(
    "branch", ["feat/model", "fix/typo", "hotfix/rollback", "chore/docs", "release/2.0"]
)
def test_validate_branch_name_accepts_cleanup_namespaces(branch: str) -> None:
    assert cleanup.validate_branch_name(branch) == branch


@pytest.mark.parametrize("branch", ["main", "topic/model", "refs/heads/fix/model", ""])
def test_validate_branch_name_rejects_unprotected_or_malformed_names(branch: str) -> None:
    with pytest.raises(ValueError):
        cleanup.validate_branch_name(branch)


def test_parse_merged_prs_returns_numbers() -> None:
    payload = (
        '[{"number": 76, "mergedAt": "2026-09-05T09:45:12Z", '
        '"headRefName": "fix/model", "headRefOid": "abc", '
        '"headRepository": {"nameWithOwner": "owner/repo"}}]'
    )
    assert cleanup.parse_merged_prs(
        payload, repo="owner/repo", branch="fix/model", head_oid="abc"
    ) == (76,)


def test_parse_merged_prs_rejects_unmerged_or_invalid_payload() -> None:
    with pytest.raises(ValueError, match="merged PR"):
        cleanup.parse_merged_prs(
            '[{"number": 76, "mergedAt": null}]',
            repo="owner/repo",
            branch="fix/model",
            head_oid="abc",
        )
