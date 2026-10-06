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


def test_platform_site_contains_only_documentation_and_report_redirect() -> None:
    workflow = (WORKFLOW_ROOT / "public-site.yml").read_text(encoding="utf-8")
    assert "build_docs_site.py" in workflow
    assert "market-intel-ledger" not in workflow
    assert "web/" not in workflow


def test_public_site_only_uploads_and_deploys_from_main() -> None:
    workflow = yaml.safe_load((WORKFLOW_ROOT / "public-site.yml").read_text(encoding="utf-8"))
    main_only = "github.ref == 'refs/heads/main' && github.event_name != 'pull_request'"
    steps = workflow["jobs"]["build"]["steps"]
    upload = next(step for step in steps if step.get("name") == "Upload Pages artifact")
    assert upload["if"] == main_only
    assert workflow["jobs"]["deploy"]["if"] == main_only
