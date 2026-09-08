from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ALLOWED_CLASSIFICATIONS = {"public", "private", "split", "remove"}


def test_manifest_classifies_every_tracked_file() -> None:
    root = Path(__file__).parents[2]
    manifest_path = root / "docs/public-release/file-migration-manifest.yml"
    manifest = yaml.safe_load(manifest_path.read_text())
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines())
    entries = manifest["files"]
    exact_paths = {entry["path"] for entry in entries if not entry["path"].endswith("/")}
    directory_paths = tuple(entry["path"] for entry in entries if entry["path"].endswith("/"))

    classified = exact_paths | {
        path for path in tracked if any(path.startswith(directory) for directory in directory_paths)
    }

    assert tracked <= classified
    assert {entry["classification"] for entry in entries} <= ALLOWED_CLASSIFICATIONS
