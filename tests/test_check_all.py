from __future__ import annotations

import importlib.util
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
