from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


install_git_hooks = _load_script(
    "test_install_git_hooks_module", "scripts/dev/install_git_hooks.py"
)


def _initialize_repositories(root: Path) -> None:
    for relative in install_git_hooks.TARGET_DIRECTORIES.values():
        repository = root / relative
        repository.mkdir(parents=True, exist_ok=True)
        subprocess.run(("git", "init", "--quiet"), cwd=repository, check=True)


def _configure_git_identity(repository: Path) -> None:
    subprocess.run(("git", "config", "user.email", "tests@example.com"), cwd=repository, check=True)
    subprocess.run(("git", "config", "user.name", "Tests"), cwd=repository, check=True)


@pytest.fixture
def hook_workspace(tmp_path: Path) -> Path:
    source = tmp_path / ".githooks" / "pre-push"
    source.parent.mkdir(parents=True)
    source.write_text(
        "#!/usr/bin/env bash\n# market-intel-managed-pre-push:v1\nexit 0\n",
        encoding="utf-8",
    )
    _initialize_repositories(tmp_path)
    return tmp_path


def _all_target_names() -> tuple[str, ...]:
    return tuple(install_git_hooks.TARGET_DIRECTORIES)


def test_installs_and_checks_all_repository_hooks(hook_workspace: Path) -> None:
    targets = install_git_hooks.install_hooks(
        root=hook_workspace,
        names=_all_target_names(),
    )

    assert len(targets) == 1
    for target in targets:
        assert install_git_hooks.MANAGED_MARKER in target.hook_path.read_text(encoding="utf-8")
        assert os.access(target.hook_path, os.X_OK)
    assert install_git_hooks.check_hooks(root=hook_workspace, names=_all_target_names())

    inodes = {target.name: target.hook_path.stat().st_ino for target in targets}
    install_git_hooks.install_hooks(root=hook_workspace, names=_all_target_names())
    assert {target.name: target.hook_path.stat().st_ino for target in targets} == inodes


def test_conflict_preflight_prevents_partial_install(hook_workspace: Path) -> None:
    target = install_git_hooks.resolve_targets(hook_workspace, _all_target_names())[0]
    target.hook_path.parent.mkdir(parents=True, exist_ok=True)
    target.hook_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Unmanaged pre-push hook"):
        install_git_hooks.install_hooks(root=hook_workspace, names=_all_target_names())

    assert target.hook_path.read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n"


def test_force_replaces_unmanaged_hook(hook_workspace: Path) -> None:
    target = install_git_hooks.resolve_targets(hook_workspace, ("root",))[0]
    target.hook_path.parent.mkdir(parents=True, exist_ok=True)
    target.hook_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    install_git_hooks.install_hooks(root=hook_workspace, names=("root",), force=True)

    assert install_git_hooks.MANAGED_MARKER in target.hook_path.read_text(encoding="utf-8")
    assert (
        target.hook_path.with_name("pre-push.before-market-intel").read_text(encoding="utf-8")
        == "#!/bin/sh\nexit 0\n"
    )


def test_dry_run_does_not_install_hook(hook_workspace: Path) -> None:
    target = install_git_hooks.resolve_targets(hook_workspace, ("root",))[0]

    install_git_hooks.install_hooks(
        root=hook_workspace,
        names=("root",),
        dry_run=True,
    )

    assert not target.hook_path.exists()


def test_windows_treats_matching_hook_content_as_executable(hook_workspace: Path) -> None:
    target = install_git_hooks.resolve_targets(hook_workspace, ("root",))[0]
    target.hook_path.parent.mkdir(parents=True, exist_ok=True)
    target.hook_path.write_text("fixture\n", encoding="utf-8")
    target.hook_path.chmod(0o600)

    assert install_git_hooks._is_executable(target.hook_path, platform="nt")
    if os.name != "nt":
        assert not install_git_hooks._is_executable(target.hook_path, platform="posix")


def test_uninstall_removes_only_managed_hooks(hook_workspace: Path) -> None:
    targets = install_git_hooks.install_hooks(
        root=hook_workspace,
        names=("root",),
    )

    install_git_hooks.uninstall_hooks(
        root=hook_workspace,
        names=("root",),
    )

    assert all(not target.hook_path.exists() for target in targets)


def test_uninstall_refuses_unmanaged_hook(hook_workspace: Path) -> None:
    target = install_git_hooks.resolve_targets(hook_workspace, ("root",))[0]
    target.hook_path.parent.mkdir(parents=True, exist_ok=True)
    target.hook_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Refusing to remove unmanaged"):
        install_git_hooks.uninstall_hooks(root=hook_workspace, names=("root",))


def test_installer_refuses_symlink_hook(hook_workspace: Path) -> None:
    target = install_git_hooks.resolve_targets(hook_workspace, ("root",))[0]
    target.hook_path.parent.mkdir(parents=True, exist_ok=True)
    destination = hook_workspace / "outside-hook"
    destination.write_text("do not replace\n", encoding="utf-8")
    try:
        target.hook_path.symlink_to(destination)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(RuntimeError, match="symlink hook"):
        install_git_hooks.install_hooks(
            root=hook_workspace,
            names=("root",),
            force=True,
        )

    assert destination.read_text(encoding="utf-8") == "do not replace\n"


def test_installer_refuses_configured_hooks_path(hook_workspace: Path) -> None:
    custom_hooks = hook_workspace / "shared-hooks"
    subprocess.run(
        ("git", "config", "core.hooksPath", str(custom_hooks)),
        cwd=hook_workspace,
        check=True,
    )

    with pytest.raises(RuntimeError, match="core.hooksPath is already configured"):
        install_git_hooks.resolve_targets(hook_workspace, ("root",))


def test_real_git_push_runs_wrapper_with_space_paths_and_blocks_dirty_tree(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    subprocess.run(("git", "init", "--quiet"), cwd=workspace, check=True)
    _configure_git_identity(workspace)
    guard = workspace / "project_tools" / "pre_push_guard.py"
    guard.parent.mkdir()
    shutil.copy2(ROOT / "project_tools" / "pre_push_guard.py", guard)
    wrapper = workspace / ".githooks" / "pre-push"
    wrapper.parent.mkdir()
    shutil.copy2(ROOT / ".githooks" / "pre-push", wrapper)
    installed_hook = workspace / ".git" / "hooks" / "pre-push"
    shutil.copy2(wrapper, installed_hook)
    installed_hook.chmod(0o755)
    (workspace / "tracked.txt").write_text("first\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=workspace, check=True)
    subprocess.run(("git", "commit", "--quiet", "-m", "initial"), cwd=workspace, check=True)
    remote = tmp_path / "remote.git"
    subprocess.run(("git", "init", "--bare", "--quiet", str(remote)), check=True)

    rejected = subprocess.run(
        ("git", "push", str(remote), "HEAD:refs/heads/topic"),
        cwd=workspace,
        text=True,
        capture_output=True,
        env={**os.environ, "MARKET_INTEL_PRE_PUSH_DRY_RUN": "1"},
        check=False,
    )

    assert rejected.returncode != 0
    assert (
        "refs/heads/main or refs/heads/{feat,fix,hotfix,release}/* are allowed"
        in rejected.stdout + rejected.stderr
    )

    completed = subprocess.run(
        ("git", "push", str(remote), "HEAD:refs/heads/main"),
        cwd=workspace,
        text=True,
        capture_output=True,
        env={**os.environ, "MARKET_INTEL_PRE_PUSH_DRY_RUN": "1"},
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--scope all" in completed.stdout + completed.stderr

    (workspace / "tracked.txt").write_text("second\n", encoding="utf-8")
    subprocess.run(("git", "commit", "--quiet", "-am", "second"), cwd=workspace, check=True)
    (workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    blocked = subprocess.run(
        ("git", "push", str(remote), "HEAD:refs/heads/main"),
        cwd=workspace,
        text=True,
        capture_output=True,
        env={**os.environ, "MARKET_INTEL_PRE_PUSH_DRY_RUN": "1"},
        check=False,
    )

    assert blocked.returncode != 0
    assert "repository is not clean" in blocked.stdout + blocked.stderr
