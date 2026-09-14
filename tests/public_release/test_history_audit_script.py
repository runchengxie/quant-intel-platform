from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "public_release" / "audit_history.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True)


def test_history_audit_reports_private_markers_without_printing_file_contents(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("private endpoint: fast.xiaodefa.cn", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "initial")
    report = tmp_path / "audit.txt"

    result = subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(repo), "--report", str(report)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "fast.xiaodefa.cn" not in result.stdout
    assert "private marker" in report.read_text(encoding="utf-8")


def test_history_audit_accepts_clean_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("public framework", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "initial")
    report = tmp_path / "audit.txt"

    result = subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(repo), "--report", str(report)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "private marker" not in report.read_text(encoding="utf-8")


def test_history_audit_ignores_marker_literals_in_audit_fixture_code(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    fixture = repo / "tests/public_release"
    fixture.mkdir(parents=True)
    (fixture / "test_marker.py").write_text('marker = "fast.xiaodefa.cn"\n', encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "initial")
    report = tmp_path / "audit.txt"

    result = subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(repo), "--report", str(report)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
