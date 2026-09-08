#!/usr/bin/env bash
set -euo pipefail

revision=""
destination=""

while (($#)); do
    case "$1" in
        --revision)
            revision="${2:-}"
            shift 2
            ;;
        --destination)
            destination="${2:-}"
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [[ -z "$revision" ]]; then
    echo "--revision is required" >&2
    exit 2
fi
if [[ -z "$destination" ]]; then
    echo "--destination is required" >&2
    exit 2
fi

source_root=$(git rev-parse --show-toplevel)
destination=$(realpath -m "$destination")
source_root=$(realpath "$source_root")
if [[ "$destination" == "$source_root" || "$destination" == "$source_root"/* ]]; then
    echo "destination must be outside the source repository" >&2
    exit 2
fi
if [[ -e "$destination" && ! -d "$destination" ]]; then
    echo "destination must be a directory" >&2
    exit 2
fi
if [[ -d "$destination" ]] && [[ -n "$(find "$destination" -mindepth 1 -print -quit)" ]]; then
    echo "destination must be empty" >&2
    exit 2
fi

tmp_root=$(mktemp -d)
trap 'rm -rf "$tmp_root"' EXIT
archive_root="$tmp_root/source"
mkdir -p "$archive_root"
git -C "$source_root" archive --format=tar "$revision" | tar -xf - -C "$archive_root"
mkdir -p "$destination"

GIT_ROOT="$source_root" SOURCE_ROOT="$archive_root" DESTINATION="$destination" REVISION="$revision" python - <<'PY'
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import yaml

source = Path(os.environ["SOURCE_ROOT"])
destination = Path(os.environ["DESTINATION"])
git_root = Path(os.environ["GIT_ROOT"])
revision = os.environ["REVISION"]
manifest = yaml.safe_load((source / "docs/public-release/file-migration-manifest.yml").read_text())
entries = manifest["files"]


def classification(path: str) -> dict[str, object] | None:
    candidates = []
    for entry in entries:
        prefix = str(entry["path"])
        if prefix.endswith("/"):
            if path.startswith(prefix):
                candidates.append((len(prefix), entry))
        elif path == prefix:
            candidates.append((len(prefix) + 10000, entry))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


tracked = subprocess.check_output(
    ["git", "-C", str(git_root), "ls-tree", "-r", "--name-only", revision], text=True
).splitlines()
for relative in tracked:
    entry = classification(relative)
    if entry is None:
        raise SystemExit(f"unclassified tracked path: {relative}")
    if entry["classification"] not in {"public", "split"}:
        continue
    source_path = source / relative
    target_path = destination / relative
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)

print(f"clean public export created at {destination}")
PY

python "$destination/scripts/public_release/check_boundary.py"
