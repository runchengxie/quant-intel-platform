"""Enforce market-intel's repository boundary with the research system."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
BOUNDARY_DOC = ROOT / "docs" / "boundary-contract.md"


def _python_files() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def _imports_from_private_research(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = (node.module or "",)
        else:
            continue
        imports.extend(
            name for name in names if name == "quant_research" or name.startswith("quant_research.")
        )
    return imports


def test_market_intel_does_not_import_private_research() -> None:
    violations = {
        str(path.relative_to(ROOT)): imports
        for path in _python_files()
        if (imports := _imports_from_private_research(path))
    }

    assert violations == {}


def test_boundary_requires_versioned_artifact_consumption() -> None:
    text = BOUNDARY_DOC.read_text(encoding="utf-8")

    assert "版本化文件产物" in text
    assert "不直接 import" in text
    assert "research-workspace" in text
    assert "market-intel" in text
