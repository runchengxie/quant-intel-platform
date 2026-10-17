"""Check that installed distributions contain all first-party runtime packages."""

from __future__ import annotations

import tomllib
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_distribution_includes_all_runtime_packages() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    discovery = config["tool"]["setuptools"]["packages"]["find"]
    includes = discovery.get("include", ["*"])
    excludes = discovery.get("exclude", [])
    missing = []
    for initializer in (ROOT / "src").rglob("__init__.py"):
        package = ".".join(initializer.parent.relative_to(ROOT / "src").parts)
        if not any(fnmatchcase(package, pattern) for pattern in includes) or any(
            fnmatchcase(package, pattern) for pattern in excludes
        ):
            missing.append(package)
    assert not missing, f"Runtime packages absent from the distribution: {sorted(missing)}"
