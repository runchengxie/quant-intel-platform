from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"


def _active_workflows() -> tuple[Path, ...]:
    return tuple(sorted(WORKFLOW_ROOT.glob("*.yml")))


def test_active_public_workflows_are_secret_free_and_read_only() -> None:
    workflows = _active_workflows()
    assert workflows
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        document = yaml.safe_load(text)
        permissions = document.get("permissions", {})
        assert permissions.get("contents") == "read", path
        assert "${{ secrets." not in text, path
        assert "contents: write" not in text, path
        assert "git push" not in text, path
        assert "feishu.cn" not in text.lower(), path
        assert "fast.xiaodefa.cn" not in text.lower(), path


def test_disabled_workflow_candidates_are_not_active_public_ci() -> None:
    disabled = tuple(sorted(WORKFLOW_ROOT.glob("*.disabled")))
    assert disabled == ()
