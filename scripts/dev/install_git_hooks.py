#!/usr/bin/env python3
"""Install market-intel's managed pre-push hook in the root repository."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANAGED_MARKER = "# market-intel-managed-pre-push:v1"
TARGET_DIRECTORIES = {"root": Path(".")}


@dataclass(frozen=True)
class HookTarget:
    name: str
    repository: Path
    hook_path: Path


def _git_hook_path(repository: Path) -> Path:
    configured = subprocess.run(
        ("git", "config", "--show-origin", "--get", "core.hooksPath"),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if configured.returncode == 0 and configured.stdout.strip():
        raise RuntimeError(
            f"{repository}: core.hooksPath is already configured ({configured.stdout.strip()})"
        )
    if configured.returncode not in {0, 1}:
        raise RuntimeError(configured.stderr.strip() or f"{repository}: cannot read core.hooksPath")
    completed = subprocess.run(
        ("git", "rev-parse", "--git-path", "hooks/pre-push"),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "not a Git worktree"
        raise RuntimeError(f"{repository}: {detail}")
    hook_path = Path(completed.stdout.strip())
    combined = hook_path if hook_path.is_absolute() else repository / hook_path
    return Path(os.path.abspath(combined))


def resolve_targets(root: Path, names: Sequence[str]) -> tuple[HookTarget, ...]:
    targets: list[HookTarget] = []
    for name in dict.fromkeys(names):
        repository = (root / TARGET_DIRECTORIES[name]).resolve()
        targets.append(HookTarget(name, repository, _git_hook_path(repository)))
    return tuple(targets)


def _read_hook(path: Path) -> str | None:
    if path.is_symlink():
        raise RuntimeError(f"Refusing to replace symlink hook: {path}")
    if not path.exists():
        return None
    if not path.is_file():
        raise RuntimeError(f"Refusing to replace non-regular hook: {path}")
    return path.read_text(encoding="utf-8")


def _is_managed(content: str | None) -> bool:
    return bool(content and MANAGED_MARKER in content.splitlines()[:3])


def _is_executable(path: Path, *, platform: str = os.name) -> bool:
    if platform == "nt":
        return True
    return bool(path.stat().st_mode & stat.S_IXUSR)


def _atomic_write_hook(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=".pre-push.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o755)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _backup_hook(path: Path) -> Path:
    candidate = path.with_name(f"{path.name}.before-market-intel")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.before-market-intel.{suffix}")
        suffix += 1
    shutil.copy2(path, candidate)
    return candidate


def install_hooks(
    *,
    root: Path,
    names: Sequence[str],
    force: bool = False,
    dry_run: bool = False,
) -> tuple[HookTarget, ...]:
    source_content = (root / ".githooks" / "pre-push").read_text(encoding="utf-8")
    targets = resolve_targets(root, names)
    existing = {target: _read_hook(target.hook_path) for target in targets}
    conflicts = [
        target
        for target, content in existing.items()
        if content is not None and not _is_managed(content) and content != source_content
    ]
    if conflicts and not force:
        paths = ", ".join(str(target.hook_path) for target in conflicts)
        raise RuntimeError(f"Unmanaged pre-push hook exists; use --force to replace: {paths}")

    for target in targets:
        content = existing[target]
        if dry_run:
            action = "would-update" if content is not None else "would-install"
            print(f"[{action}] {target.name}: {target.hook_path}")
            continue
        if content is not None and not _is_managed(content) and content != source_content:
            backup_path = _backup_hook(target.hook_path)
            print(f"[backup] {target.name}: {backup_path}")
        if content != source_content or not _is_executable(target.hook_path):
            _atomic_write_hook(target.hook_path, source_content)
        print(f"[installed] {target.name}: {target.hook_path}")
    return targets


def check_hooks(*, root: Path, names: Sequence[str]) -> bool:
    source_content = (root / ".githooks" / "pre-push").read_text(encoding="utf-8")
    all_current = True
    for target in resolve_targets(root, names):
        content = _read_hook(target.hook_path)
        current = content == source_content and _is_executable(target.hook_path)
        print(f"[{'ok' if current else 'missing-or-stale'}] {target.name}: {target.hook_path}")
        all_current = all_current and current
    return all_current


def uninstall_hooks(*, root: Path, names: Sequence[str]) -> None:
    for target in resolve_targets(root, names):
        content = _read_hook(target.hook_path)
        if content is None:
            print(f"[absent] {target.name}: {target.hook_path}")
            continue
        if not _is_managed(content):
            raise RuntimeError(f"Refusing to remove unmanaged pre-push hook: {target.hook_path}")
        target.hook_path.unlink()
        print(f"[removed] {target.name}: {target.hook_path}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        action="append",
        choices=tuple(TARGET_DIRECTORIES),
        help="Repository to configure (only root is managed)",
    )
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--check", action="store_true", help="Verify without changing hooks")
    operation.add_argument("--uninstall", action="store_true", help="Remove managed hooks")
    operation.add_argument("--dry-run", action="store_true", help="Show installation actions")
    parser.add_argument("--force", action="store_true", help="Replace an unmanaged pre-push hook")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    names = args.target or tuple(TARGET_DIRECTORIES)
    try:
        if args.check:
            return 0 if check_hooks(root=ROOT, names=names) else 1
        if args.uninstall:
            if args.force:
                raise ValueError("--force cannot be combined with --uninstall")
            uninstall_hooks(root=ROOT, names=names)
            return 0
        install_hooks(root=ROOT, names=names, force=args.force, dry_run=args.dry_run)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[git-hooks] FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
