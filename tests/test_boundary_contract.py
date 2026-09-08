from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
FORBIDDEN_IMPORT_PREFIXES = (
    "alpha_research",
    "portfolio_backtester",
    "strategy_app",
    "strategy_pipeline",
    "ticknet",
)


def _python_files() -> list[Path]:
    return sorted((*((ROOT / "src").rglob("*.py")), *((ROOT / "scripts").rglob("*.py"))))


def test_market_intel_does_not_import_research_owner_implementations() -> None:
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {name}")

    assert violations == [], (
        "market-intel must consume owner artifacts/CLIs, not owner imports:\n"
        + "\n".join(violations)
    )


def test_market_intel_does_not_hardcode_workspace_paths() -> None:
    violations: list[str] = []
    forbidden_fragments = (
        'Path.home() / "code" / "research-workspace"',
        "$HOME/code/research-workspace",
        "/home/richard/code/research-workspace",
    )
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        if any(fragment in text for fragment in forbidden_fragments):
            violations.append(str(path.relative_to(ROOT)))

    assert violations == [], "workspace paths must come from deployment configuration:\n" + "\n".join(violations)
