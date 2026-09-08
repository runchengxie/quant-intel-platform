from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_all = _load_script("test_check_all", "project_tools/check_all.py")
pre_push_guard = _load_script("test_pre_push_guard_module", "project_tools/pre_push_guard.py")


def _push_line(remote_ref: str, *, local_sha: str = "1" * 40) -> str:
    return f"refs/heads/topic {local_sha} {remote_ref} {'2' * 40}\n"


def _initialize_committed_repository(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(("git", "init", "--quiet"), cwd=path, check=True)
    subprocess.run(("git", "config", "user.email", "tests@example.com"), cwd=path, check=True)
    subprocess.run(("git", "config", "user.name", "Tests"), cwd=path, check=True)
    (path / "tracked.txt").write_text("first\n", encoding="utf-8")
    subprocess.run(("git", "add", "tracked.txt"), cwd=path, check=True)
    subprocess.run(("git", "commit", "--quiet", "-m", "initial"), cwd=path, check=True)
    return subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_parse_push_updates_rejects_malformed_input() -> None:
    with pytest.raises(ValueError, match="expected 4 fields"):
        pre_push_guard.parse_push_updates("refs/heads/topic only-two-fields\n")


@pytest.mark.parametrize(
    "remote_ref",
    ["refs/heads/topic", "refs/heads/refactor/nope"],
)
def test_push_destination_rejects_unprefixed_remote_refs(remote_ref: str) -> None:
    updates = pre_push_guard.parse_push_updates(_push_line(remote_ref))
    with pytest.raises(ValueError, match="only refs/heads/main or"):
        pre_push_guard.validate_push_destinations(updates)


@pytest.mark.parametrize(
    "remote_ref",
    [
        "refs/heads/feat/add-report",
        "refs/heads/fix/typo",
        "refs/heads/hotfix/rollback",
        "refs/heads/chore/docs",
        "refs/heads/release/2.0",
        "refs/heads/main",
        "refs/tags/v1.0.0",
    ],
)
def test_push_destination_accepts_whitelisted_branch_and_tag_creation(remote_ref: str) -> None:
    updates = pre_push_guard.parse_push_updates(_push_line(remote_ref))
    pre_push_guard.validate_push_destinations(updates)


@pytest.mark.parametrize(
    "remote_ref",
    [
        "refs/heads/main",
        "refs/tags/v1.0.0",
    ],
)
def test_push_destination_rejects_main_and_tag_deletion(remote_ref: str) -> None:
    updates = pre_push_guard.parse_push_updates(_push_line(remote_ref, local_sha="0" * 40))
    with pytest.raises(ValueError, match="deleting remote"):
        pre_push_guard.validate_push_destinations(updates)


@pytest.mark.parametrize(
    "remote_ref",
    [
        "refs/heads/feat/merged-pr",
        "refs/heads/fix/merged-pr",
        "refs/heads/hotfix/merged-pr",
        "refs/heads/release/merged-pr",
    ],
)
def test_push_destination_allows_feature_branch_deletion(remote_ref: str) -> None:
    updates = pre_push_guard.parse_push_updates(_push_line(remote_ref, local_sha="0" * 40))
    pre_push_guard.validate_push_destinations(updates)


def test_root_release_push_runs_full_check() -> None:
    updates = pre_push_guard.parse_push_updates(_push_line("refs/heads/main"))
    assert pre_push_guard.command_for_push("root", updates) == (
        "uv",
        "run",
        "python",
        "project_tools/check_all.py",
        "--scope",
        "all",
    )


def test_feature_push_runs_root_check_with_non_python_validation() -> None:
    updates = pre_push_guard.parse_push_updates(_push_line("refs/heads/fix/root-only"))
    assert pre_push_guard.command_for_push("root", updates) == (
        "uv",
        "run",
        "python",
        "project_tools/check_all.py",
        "--project",
        "root",
        "--include-non-python",
    )


def test_non_root_project_is_rejected() -> None:
    updates = pre_push_guard.parse_push_updates(_push_line("refs/heads/main"))
    with pytest.raises(ValueError, match="Unsupported project"):
        pre_push_guard.command_for_push("hot-sector-screener", updates)


def test_repository_mapping_is_root_only(tmp_path: Path) -> None:
    assert pre_push_guard.project_for_repository(tmp_path, root=tmp_path) == "root"
    with pytest.raises(ValueError, match="Unsupported repository"):
        pre_push_guard.project_for_repository(tmp_path / "hot-sector-screener", root=tmp_path)


def test_push_state_requires_clean_repository(tmp_path: Path) -> None:
    head = _initialize_committed_repository(tmp_path)
    updates = pre_push_guard.parse_push_updates(_push_line("refs/heads/fix/test", local_sha=head))
    (tmp_path / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repository is not clean"):
        pre_push_guard.validate_push_state(tmp_path, updates)


def test_push_state_requires_pushed_commit_to_equal_head(tmp_path: Path) -> None:
    previous_head = _initialize_committed_repository(tmp_path)
    (tmp_path / "tracked.txt").write_text("second\n", encoding="utf-8")
    subprocess.run(("git", "commit", "--quiet", "-am", "second"), cwd=tmp_path, check=True)
    updates = pre_push_guard.parse_push_updates(
        _push_line("refs/heads/fix/test", local_sha=previous_head)
    )
    with pytest.raises(ValueError, match="does not resolve to the checked-out HEAD"):
        pre_push_guard.validate_push_state(tmp_path, updates)


def test_remote_quality_policy_scans_market_intel_only(tmp_path: Path) -> None:
    root_workflow = tmp_path / ".github" / "workflows" / "quality.yml"
    root_workflow.parent.mkdir(parents=True)
    root_workflow.write_text(
        "jobs:\n  lint:\n    steps:\n      - run: ruff check .\n", encoding="utf-8"
    )
    child_workflow = tmp_path / "hot-sector-screener" / ".github" / "workflows" / "ci.yml"
    child_workflow.parent.mkdir(parents=True)
    child_workflow.write_text(
        "jobs:\n  lint:\n    steps:\n      - run: ruff check .\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="quality.yml") as exc_info:
        pre_push_guard.validate_local_only_quality_policy(
            project="root", repository=tmp_path, root=tmp_path
        )
    assert "hot-sector-screener" not in str(exc_info.value)


def test_skip_flag_bypasses_command_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = pre_push_guard.run_guard(
        repository=tmp_path,
        payload=_push_line("refs/heads/main"),
        environ={"SKIP_LOCAL_CHECKS": "1"},
        root=tmp_path,
    )
    assert result == 0
    assert "WARNING: skipping local checks" in capsys.readouterr().err


def test_dry_run_prints_without_spawning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        pre_push_guard,
        "validate_push_state",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pre_push_guard,
        "validate_local_only_quality_policy",
        lambda *args, **kwargs: None,
    )
    result = pre_push_guard.run_guard(
        repository=tmp_path,
        payload=_push_line("refs/heads/main"),
        environ={"MARKET_INTEL_PRE_PUSH_DRY_RUN": "yes"},
        root=tmp_path,
    )
    assert result == 0
    output = capsys.readouterr().out
    assert "--scope all" in output
    assert "dry-run" in output


def test_failed_check_blocks_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_run(command: tuple[str, ...], *, cwd: Path, check: bool) -> SimpleNamespace:
        calls.append((command, cwd))
        assert check is False
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(pre_push_guard.subprocess, "run", fake_run)
    monkeypatch.setattr(pre_push_guard, "validate_push_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pre_push_guard,
        "validate_local_only_quality_policy",
        lambda *args, **kwargs: None,
    )

    result = pre_push_guard.run_guard(
        repository=tmp_path,
        payload=_push_line("refs/heads/main"),
        environ={},
        root=tmp_path,
    )
    assert result == 7
    assert calls[0][0][-2:] == ("--scope", "all")
    assert calls[0][1] == tmp_path
    assert "push blocked" in capsys.readouterr().err


def test_check_all_accepts_root_project_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_all, "_run_root", lambda: 0)
    monkeypatch.setattr(
        check_all,
        "_run_non_python",
        lambda strict_tools: pytest.fail(f"unexpected non-python checks: {strict_tools}"),
    )
    assert check_all.main(["--project", "root"]) == 0
    with pytest.raises(SystemExit):
        check_all.parse_args(["--project", "hot-sector-screener"])
