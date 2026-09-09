"""Compare two frozen Quant artifact roots and write a parity manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .compare import compare_artifacts

DEFAULT_IGNORED_FIELDS = {"generated_at", "message_id", "message_ids", "run_id"}
DEFAULT_PATH_FIELDS = {"paths"}


def _git_commit(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def _json_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*.json"))
        if path.is_file()
    }


def build_parity_manifest(
    *,
    source_date: str,
    signal_date: str,
    old_root: Path,
    new_root: Path,
    ignored_fields: set[str] | None = None,
    path_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Compare JSON artifacts already produced under two isolated roots."""
    old_files = _json_files(old_root)
    new_files = _json_files(new_root)
    mandatory_paths = sorted(set(old_files) | set(new_files))
    differences: dict[str, list[str]] = {}
    missing_old: list[str] = []
    missing_new: list[str] = []
    fields = DEFAULT_IGNORED_FIELDS | (ignored_fields or set())

    for relative_path in mandatory_paths:
        old_path = old_files.get(relative_path)
        new_path = new_files.get(relative_path)
        if old_path is None:
            missing_old.append(relative_path)
        elif new_path is None:
            missing_new.append(relative_path)
        else:
            found = compare_artifacts(
                old_path,
                new_path,
                ignored_fields=fields,
                path_fields=DEFAULT_PATH_FIELDS | (path_fields or set()),
            )
            if found:
                differences[relative_path] = found

    unexplained = bool(missing_old or missing_new or differences)
    return {
        "schema_version": "quant.production.parity.v1",
        "source_date": source_date,
        "signal_date": signal_date,
        "generated_at": datetime.now(UTC).isoformat(),
        "old": {"root": str(old_root), "commit": _git_commit(old_root)},
        "new": {"root": str(new_root), "commit": _git_commit(new_root)},
        "mandatory_artifacts": mandatory_paths,
        "missing_from_old": missing_old,
        "missing_from_new": missing_new,
        "differences": differences,
        "unexplained_differences": unexplained,
    }


def run(args: argparse.Namespace) -> int:
    old_root = args.old_root.expanduser().resolve()
    new_root = args.new_root.expanduser().resolve()
    if not old_root.is_dir() or not new_root.is_dir():
        raise ValueError("old-root and new-root must both be directories")
    manifest = build_parity_manifest(
        source_date=args.source_date,
        signal_date=args.signal_date,
        old_root=old_root,
        new_root=new_root,
        ignored_fields=set(args.ignore_field),
        path_fields=set(args.path_field),
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    output_path = args.output_root / f"parity_{args.source_date}_{args.signal_date}.json"
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output_path)
    return 1 if manifest["unexplained_differences"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--old-root", required=True, type=Path)
    parser.add_argument("--new-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--ignore-field", action="append", default=[])
    parser.add_argument(
        "--path-field",
        action="append",
        default=[],
        help="mapping field under which absolute artifact paths are compared by basename",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
