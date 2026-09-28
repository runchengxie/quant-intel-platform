"""Verify the chart subset of a built Pages artifact before publication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .chart_contract import validate_public_chart
except ImportError:
    from chart_contract import validate_public_chart


def audit_chart_artifact(output: Path) -> dict:
    output = output.resolve()
    index = json.loads((output / "data/reports.json").read_text(encoding="utf-8"))
    report_ids = {item["id"] for item in index["reports"] if isinstance(item, dict)}
    chart_dir = output / "data/charts"
    if not chart_dir.exists():
        return {"chart_count": 0, "report_ids": []}
    found: list[str] = []
    for path in sorted(chart_dir.iterdir()):
        report_id = path.stem
        if path.suffix != ".json" or report_id not in report_ids or not path.is_file():
            raise ValueError(f"chart identity or file type is unsafe: {path.name}")
        if not path.resolve().is_relative_to(chart_dir.resolve()):
            raise ValueError(f"unsafe chart path: {path.name}")
        validate_public_chart(json.loads(path.read_text(encoding="utf-8")), expected_id=report_id)
        found.append(report_id)
    return {"chart_count": len(found), "report_ids": found}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_chart_artifact(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
