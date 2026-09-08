from __future__ import annotations

from pathlib import Path


def test_public_docs_have_no_private_markers() -> None:
    root = Path(__file__).parents[2]
    files = [root / "README.md", *sorted((root / "docs").glob("*.md"))]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files if path.exists())

    for marker in ("凯川", "kaichuan", "fast.xiaodefa.cn", "my.feishu.cn/docx/"):
        assert marker.lower() not in text.lower()
