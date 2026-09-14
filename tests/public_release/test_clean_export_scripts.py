from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "public_release" / "build_clean_export.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_export_requires_an_explicit_revision_and_destination(tmp_path: Path) -> None:
    missing_revision = _run("--destination", str(tmp_path / "export"))
    assert missing_revision.returncode != 0
    assert "--revision is required" in missing_revision.stderr

    missing_destination = _run("--revision", "HEAD")
    assert missing_destination.returncode != 0
    assert "--destination is required" in missing_destination.stderr


def test_clean_export_rejects_non_empty_destination(tmp_path: Path) -> None:
    destination = tmp_path / "export"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep", encoding="utf-8")

    result = _run("--revision", "HEAD", "--destination", str(destination))

    assert result.returncode != 0
    assert "destination must be empty" in result.stderr


def test_clean_export_omits_private_process_docs_and_scheduler_assets(tmp_path: Path) -> None:
    destination = tmp_path / "export"

    result = _run("--revision", "HEAD", "--destination", str(destination))

    assert result.returncode == 0, result.stderr
    assert (destination / "src").is_dir()
    assert (destination / "tests/public_release").is_dir()
    assert not (destination / "docs/superpowers").exists()
    assert not (destination / "scripts/systemd").exists()
    assert not (destination / "scripts/windows").exists()
    assert not (destination / "scripts/setup_cron.sh").exists()
    assert not (destination / "tests/test_scheduled_recovery.py").exists()
    assert not (destination / ".git").exists()
