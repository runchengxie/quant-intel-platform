#!/usr/bin/env python3
"""Run market-intel's repository-local quality checks.

Research repositories own their own gates inside research-workspace. This script
therefore checks market-intel only; it no longer reaches into adjacent owner
repositories or git submodules.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("uv", "run", "ruff", "check", "."),
    ("uv", "run", "ruff", "format", "--check", "."),
    ("uv", "run", "python", "project_tools/update_cli_help.py", "--check"),
    ("uv", "run", "ty", "check"),
    ("uv", "run", "python", "scripts/dev/maintainability_metrics.py", "--ratchet"),
    ("uv", "run", "pytest", "--cov-report=term-missing"),
)


def _print_header(title: str) -> None:
    print(f"\n== {title} ==", flush=True)


def _run(command: Sequence[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> int:
    print(f"+ {' '.join(command)}  [{cwd.relative_to(ROOT) if cwd != ROOT else '.'}]", flush=True)
    return subprocess.run(command, cwd=cwd, env=env, check=False).returncode


def _run_root() -> int:
    if not (ROOT / "pyproject.toml").exists():
        print(f"[FAIL] missing pyproject.toml at {ROOT}", file=sys.stderr)
        return 1
    _print_header("root")
    for command in ROOT_COMMANDS:
        code = _run(command)
        if code != 0:
            return code
    return 0


def _files(patterns: Iterable[str]) -> list[str]:
    paths: set[str] = set()
    for pattern in patterns:
        paths.update(
            path.relative_to(ROOT).as_posix() for path in ROOT.glob(pattern) if path.is_file()
        )
    return sorted(paths)


def _run_if_available(
    tool: str,
    command: Sequence[str],
    *,
    strict: bool,
    env: dict[str, str] | None = None,
) -> int:
    if shutil.which(tool) is None:
        if strict:
            print(f"[FAIL] {tool} not found", file=sys.stderr)
            return 1
        print(f"[SKIP] {tool} not found")
        return 0
    return _run(command, env=env)


def _check_shell_scripts(strict_tools: bool) -> int:
    shell_files = _files(("scripts/*.sh", "scripts/**/*.sh"))
    if not shell_files:
        return 0
    _print_header("shell scripts")
    if shutil.which("bash") is None:
        return 1 if strict_tools else 0
    code = _run(("bash", "-n", *shell_files))
    if code != 0:
        return code
    code = _run_if_available("shellcheck", ("shellcheck", *shell_files), strict=strict_tools)
    if code != 0:
        return code
    return _run_if_available("shfmt", ("shfmt", "-d", *shell_files), strict=False)


def _check_powershell_scripts(strict_tools: bool) -> int:
    ps_files = _files(("scripts/**/*.ps1",))
    if not ps_files:
        return 0
    _print_header("powershell scripts")
    script = r"""
$ErrorActionPreference = 'Stop'
$ok = $true
Get-ChildItem -Path (Join-Path $env:MI_ROOT 'scripts') -Filter *.ps1 -Recurse | ForEach-Object {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$errors) | Out-Null
    if ($errors.Count -gt 0) { $ok = $false; foreach ($err in $errors) { Write-Error "$($_.FullName): $($err.Message)" } }
}
if (-not $ok) { exit 1 }
"""
    env = dict(os.environ)
    env["MI_ROOT"] = str(ROOT)
    return _run_if_available(
        "pwsh", ("pwsh", "-NoProfile", "-Command", script), strict=strict_tools, env=env
    )


def _check_javascript(strict_tools: bool) -> int:
    for file_path in _files(("project_tools/*.js",)):
        code = _run_if_available("node", ("node", "--check", file_path), strict=strict_tools)
        if code != 0:
            return code
    return 0


def _run_non_python(strict_tools: bool) -> int:
    for check in (_check_shell_scripts, _check_powershell_scripts, _check_javascript):
        code = check(strict_tools)
        if code != 0:
            return code
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=("all", "root", "python", "non-python"),
        default="all",
    )
    parser.add_argument("--strict-tools", action="store_true")
    parser.add_argument("--include-non-python", action="store_true")
    # Compatibility with the old root/submodule interface. Only root is valid now.
    parser.add_argument("--project", action="append", choices=("root",))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.scope in {"all", "root", "python"} or args.project:
        code = _run_root()
        if code != 0:
            return code
    if args.include_non_python or (not args.project and args.scope in {"all", "non-python"}):
        return _run_non_python(strict_tools=args.strict_tools)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
