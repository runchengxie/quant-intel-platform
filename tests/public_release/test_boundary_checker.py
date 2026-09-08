from __future__ import annotations

from pathlib import Path

from scripts.public_release.check_boundary import check_tree


def test_boundary_checker_rejects_private_marker(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "internal endpoint: https://fast.xiaodefa.cn", encoding="utf-8"
    )

    result = check_tree(tmp_path)

    assert "fast.xiaodefa.cn" in result.forbidden_matches


def test_boundary_checker_accepts_generic_example(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "MARKET_INTEL_CLIENT_CHAT_ID=example", encoding="utf-8"
    )

    result = check_tree(tmp_path)

    assert result.forbidden_matches == ()


def test_boundary_checker_rejects_credential_shaped_tokens(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "github_token=ghp_123456789012345678901234567890123456", encoding="utf-8"
    )

    result = check_tree(tmp_path)

    assert "ghp_[A-Za-z0-9]{20,}" in result.forbidden_matches


def test_boundary_checker_skips_private_export_candidates(tmp_path: Path) -> None:
    private_script = tmp_path / "scripts" / "systemd" / "service"
    private_script.parent.mkdir(parents=True)
    private_script.write_text("https://fast.xiaodefa.cn", encoding="utf-8")

    result = check_tree(tmp_path)

    assert result.forbidden_matches == ()
