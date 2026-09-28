"""Map public URL-relative paths to the reviewed snapshot in the checkout."""

from __future__ import annotations

from pathlib import Path


def public_snapshot_root(repo_root: Path) -> Path:
    return repo_root / "artifacts" / "public"


def safe_public_report_path(repo_root: Path, source_url: str) -> Path:
    source = Path(source_url)
    if source.is_absolute() or len(source.parts) != 2 or source.parts[0] != "reports":
        raise ValueError(f"invalid report source path: {source_url}")
    if source.parts[1] in (".", "..") or source.suffix != ".md":
        raise ValueError(f"invalid report source path: {source_url}")
    root = public_snapshot_root(repo_root) / "reports"
    resolved = (public_snapshot_root(repo_root) / source).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"invalid report source path: {source_url}")
    return resolved
