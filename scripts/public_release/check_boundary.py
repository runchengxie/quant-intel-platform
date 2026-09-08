from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_MARKERS = (
    "fast.xiaodefa.cn",
    "my.feishu.cn/docx/",
    "kaichuan",
    "凯川",
    "token_label",
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
)
FORBIDDEN_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xoxb-[0-9A-Za-z-]{20,}"),
)
SKIP_PREFIXES = (
    "scripts/",
    ".github/workflows/",
    "docs/superpowers/",
    "docs/public-release/private-migration-notes.md",
    "tests/public_release/",
    ".venv/",
    "build/",
    "dist/",
)


@dataclass(frozen=True)
class BoundaryResult:
    forbidden_matches: tuple[str, ...]
    locations: tuple[str, ...]


def _is_skipped(relative_path: str) -> bool:
    return relative_path.startswith(SKIP_PREFIXES)


def check_tree(root: Path) -> BoundaryResult:
    matches: set[str] = set()
    locations: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if _is_skipped(relative) or ".git/" in f"{relative}/":
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "\x00" in content:
            continue
        lower_content = content.lower()
        for marker in FORBIDDEN_MARKERS:
            if marker.lower() in lower_content:
                matches.add(marker)
                locations.append(f"{relative}: {marker}")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(content):
                matches.add(pattern.pattern)
                locations.append(f"{relative}: {pattern.pattern}")
    return BoundaryResult(tuple(sorted(matches)), tuple(sorted(locations)))


def main() -> int:
    result = check_tree(Path.cwd())
    if not result.locations:
        print("public boundary check passed")
        return 0
    print("public boundary check failed:", file=sys.stderr)
    print("\n".join(result.locations), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
