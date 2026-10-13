from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "test_check_all_module", ROOT / "project_tools/check_all.py"
)
assert SPEC is not None and SPEC.loader is not None
check_all = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_all
SPEC.loader.exec_module(check_all)


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("all", ["python", "non-python"]),
        ("root", ["python"]),
        ("python", ["python"]),
        ("non-python", ["non-python"]),
    ],
)
def test_scope_runs_the_configured_gate_sections(
    monkeypatch: pytest.MonkeyPatch, scope: str, expected: list[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(check_all, "_run_root", lambda: calls.append("python") or 0)
    monkeypatch.setattr(
        check_all,
        "_run_non_python",
        lambda strict_tools: calls.append("non-python") or 0,
    )

    assert check_all.main(["--scope", scope]) == 0
    assert calls == expected


def test_removed_project_compat_flag_is_rejected() -> None:
    with pytest.raises(SystemExit):
        check_all.parse_args(["--project", "root"])


def test_shell_syntax_checks_every_discovered_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is required for shell syntax validation")
    first = tmp_path / "first.sh"
    second = tmp_path / "second.sh"
    first.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    second.write_text("#!/usr/bin/env bash\nif true; then\n", encoding="utf-8")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "bash").symlink_to(bash)
    monkeypatch.setenv("PATH", str(tools))
    monkeypatch.setattr(check_all, "_files", lambda _: [str(first), str(second)])

    assert check_all._check_shell_scripts(strict_tools=False) != 0
