"""Build the report manifest consumed by the evening delivery contract."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


def _normalise_date(value: Any) -> str:
    value_text = str(value or "")
    if not re.fullmatch(r"(?:\d{8}|\d{4}-\d{2}-\d{2})", value_text):
        raise ValueError(f"invalid manifest date format: {value!r}")
    raw = value_text.replace("-", "")
    try:
        parsed = datetime.strptime(raw, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"invalid manifest date: {value!r}") from exc
    return parsed.strftime("%Y%m%d")


def build_evening_manifest(
    source_payload: Mapping[str, Any], *, expected_date: str
) -> dict[str, Any]:
    """Convert the morning chart-generation payload into an evening manifest."""
    actual_date = _normalise_date(source_payload.get("date"))
    target_date = _normalise_date(expected_date)
    if actual_date != target_date:
        raise ValueError(f"manifest date {actual_date!r} != expected {target_date!r}")

    manifest = dict(source_payload)
    manifest["pipeline"] = "evening"
    manifest["report_kind"] = "evening"
    manifest["source_pipeline"] = "morning_chart_generation"
    return manifest


def write_evening_manifest(
    source_path: Path, output_path: Path, *, expected_date: str
) -> None:
    """Read a chart-generation payload and atomically publish an evening manifest."""
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid chart-generation manifest: {source_path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"chart-generation manifest must be an object: {source_path}")

    manifest = build_evening_manifest(payload, expected_date=expected_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(json.dumps(manifest, ensure_ascii=False, indent=2))
            temporary_file.write("\n")
            temporary_file.flush()
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    write_evening_manifest(args.source, args.output, expected_date=args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
