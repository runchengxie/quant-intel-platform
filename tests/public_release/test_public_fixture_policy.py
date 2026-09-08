from __future__ import annotations

from pathlib import Path


def test_public_fixtures_contain_no_private_markers() -> None:
    root = Path(__file__).parents[2]
    fixture_root = root / "tests/fixtures/public"
    assert fixture_root.is_dir()
    assert tuple(fixture_root.rglob("*"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in fixture_root.rglob("*"))

    for marker in ("fast.xiaodefa.cn", "feishu.cn", "凯川", "kaichuan", "token_label"):
        assert marker.lower() not in text.lower()


def test_public_fixtures_are_small() -> None:
    root = Path(__file__).parents[2]
    fixture_root = root / "tests/fixtures/public"
    assert fixture_root.is_dir()
    assert tuple(fixture_root.rglob("*"))

    assert all(path.stat().st_size < 100_000 for path in fixture_root.rglob("*"))
