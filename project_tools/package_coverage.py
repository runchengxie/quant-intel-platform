#!/usr/bin/env python3
"""Enforce minimum line coverage for each production package."""

from __future__ import annotations

import json
import sys
import tempfile
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from coverage import Coverage, CoverageException

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_MINIMUMS = {
    "a_share_analysis": 70.0,
    "a_share_daily": 65.0,
    "daily_messenger": 65.0,
    "ops_common": 50.0,
    "tushare_jobs": 35.0,
}


def package_coverage_percentages(
    report_files: Mapping[str, Mapping[str, Any]],
) -> dict[str, float]:
    """Return statement-weighted line coverage for source packages."""
    counts: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    for filename, details in report_files.items():
        parts = Path(filename).parts
        if len(parts) < 3 or parts[0] != "src":
            continue
        summary = details["summary"]
        package = parts[1]
        counts[package][0] += int(summary["covered_lines"])
        counts[package][1] += int(summary["num_statements"])

    return {
        package: covered * 100.0 / statements
        for package, (covered, statements) in sorted(counts.items())
        if statements > 0
    }


def package_threshold_violations(
    percentages: Mapping[str, float],
    *,
    thresholds: Mapping[str, float] = PACKAGE_MINIMUMS,
) -> list[str]:
    """Describe package floors that are missed or lack measured source files."""
    violations = []
    for package, minimum in sorted(thresholds.items()):
        actual = percentages.get(package)
        if actual is None:
            violations.append(f"{package}: no source files were measured")
        elif actual < minimum:
            violations.append(f"{package}: {actual:.1f}% is below the {minimum:.1f}% minimum")
    return violations


def _coverage_report_files() -> Mapping[str, Mapping[str, Any]]:
    data_file = ROOT / ".coverage"
    if not data_file.is_file():
        raise CoverageException("coverage data is missing; run pytest with --cov first")

    coverage = Coverage(config_file=str(ROOT / "pyproject.toml"), data_file=str(data_file))
    coverage.load()
    with tempfile.TemporaryDirectory(prefix="market-intel-coverage-") as temp_dir:
        output = Path(temp_dir) / "coverage.json"
        coverage.json_report(outfile=str(output))
        report = json.loads(output.read_text(encoding="utf-8"))
    return report["files"]


def main() -> int:
    try:
        percentages = package_coverage_percentages(_coverage_report_files())
    except (CoverageException, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"[FAIL] cannot read package coverage: {exc}", file=sys.stderr)
        return 1

    for package, minimum in sorted(PACKAGE_MINIMUMS.items()):
        actual = percentages.get(package)
        if actual is not None:
            print(f"[coverage] {package}: {actual:.2f}% (minimum {minimum:.1f}%)")

    violations = package_threshold_violations(percentages)
    if violations:
        for violation in violations:
            print(f"[FAIL] {violation}", file=sys.stderr)
        return 1

    print("[PASS] all production package coverage minimums met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
