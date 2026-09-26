"""Prevent ignored PLR0911/PLR0913 complexity debt from increasing."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "scripts" / "dev" / "ruff_plr_baseline.json"
RULES = "PLR0911,PLR0913"


def _collect_diagnostics() -> dict[str, int]:
    command = [
        "ruff",
        "check",
        "src",
        "tests",
        "scripts",
        "project_tools",
        "--extend-select",
        RULES,
        "--output-format",
        "json",
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"ruff failed (exit {result.returncode}):\n{result.stderr}")
    diagnostics: list[dict[str, Any]] = json.loads(result.stdout or "[]")
    counts: Counter[str] = Counter()
    for diagnostic in diagnostics:
        code = diagnostic.get("code")
        if code not in {"PLR0911", "PLR0913"}:
            continue
        filename = Path(diagnostic["filename"]).resolve()
        path = filename.relative_to(REPO_ROOT).as_posix()
        counts[f"{path}::{code}"] += 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write-baseline", action="store_true")
    mode.add_argument("--check-baseline", action="store_true")
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    args = parser.parse_args()
    baseline_path = args.baseline if args.baseline.is_absolute() else REPO_ROOT / args.baseline

    try:
        current = _collect_diagnostics()
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"Ruff PLR ratchet failed: {exc}", file=sys.stderr)
        return 1

    if args.write_baseline:
        payload = {"generated_on": date.today().isoformat(), "diagnostics": current}
        baseline_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(
            f"Wrote {sum(current.values())} Ruff PLR diagnostics to {baseline_path.relative_to(REPO_ROOT)}"
        )
        return 0

    try:
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline = {str(key): int(value) for key, value in payload["diagnostics"].items()}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"cannot read Ruff PLR baseline {baseline_path}: {exc}", file=sys.stderr)
        return 1

    regressions = [
        (key, count, baseline.get(key, 0))
        for key, count in current.items()
        if count > baseline.get(key, 0)
    ]
    if regressions:
        for key, count, accepted in regressions:
            print(f"{key}: {count} > {accepted}", file=sys.stderr)
        return 1
    print(f"Ruff PLR ratchet passed: {sum(current.values())} diagnostics, no baseline increases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
