from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from project_tools import build_docs_site


def test_build_docs_site_keeps_docs_and_adds_root_redirect(tmp_path, monkeypatch) -> None:
    output = tmp_path / "site"

    def fake_run(command, *, cwd, check):
        assert command[1:4] == ["-m", "mkdocs", "build"]
        assert cwd == build_docs_site.ROOT
        assert check is True
        docs = Path(command[command.index("--site-dir") + 1])
        docs.mkdir(parents=True)
        (docs / "index.html").write_text("documentation", encoding="utf-8")

    monkeypatch.setattr(build_docs_site.subprocess, "run", fake_run)

    build_docs_site.build_docs_site(output)

    assert (output / "docs/index.html").read_text(encoding="utf-8") == "documentation"
    redirect = (output / "index.html").read_text(encoding="utf-8")
    assert build_docs_site.PAGES_URL in redirect
    assert "destination.search = window.location.search" in redirect
    assert "destination.hash = window.location.hash" in redirect


def test_build_docs_site_rejects_output_inside_repository(tmp_path) -> None:
    output = build_docs_site.ROOT / "generated-site"
    with pytest.raises(ValueError, match="outside"):
        build_docs_site.build_docs_site(output)


def test_build_docs_site_rejects_symlink_output(tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    output = tmp_path / "site-link"
    output.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        build_docs_site.build_docs_site(output)


def test_build_failure_preserves_previous_site(tmp_path, monkeypatch) -> None:
    output = tmp_path / "site"
    output.mkdir()
    (output / "index.html").write_text("existing redirect", encoding="utf-8")

    def fail_build(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "mkdocs")

    monkeypatch.setattr(build_docs_site.subprocess, "run", fail_build)

    with pytest.raises(subprocess.CalledProcessError):
        build_docs_site.build_docs_site(output)

    assert (output / "index.html").read_text(encoding="utf-8") == "existing redirect"
