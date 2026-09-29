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
    source_payload: Mapping[str, Any],
    *,
    expected_date: str,
    review_payload: Mapping[str, Any] | None = None,
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
    if review_payload is not None:
        from .charts.public_extract import extract_evening_review_points

        points = extract_evening_review_points(review_payload, target_date)
        charts = dict(manifest.get("charts", {}))
        public_points = dict(charts.get("public_points", {}))
        public_points.update(points)
        charts["public_points"] = public_points
        charts["ok"] = sorted(set(charts.get("ok", [])) | {"topic", "sentiment"})
        charts["failed"] = [
            key for key in charts.get("failed", []) if key not in {"topic", "sentiment"}
        ]
        charts["skipped"] = [
            key for key in charts.get("skipped", []) if key not in {"topic", "sentiment"}
        ]
        errors = dict(charts.get("errors", {}))
        errors.pop("topic", None)
        errors.pop("sentiment", None)
        charts["errors"] = errors
        manifest["charts"] = charts
        manifest["public_chart_sources"] = {
            "topic": "东方财富概念板块（Tushare 授权数据）",
            "sentiment": "Tushare A股晚报六维观察",
        }
    return manifest


def write_evening_manifest(
    source_path: Path,
    output_path: Path,
    *,
    expected_date: str,
    review_path: Path | None = None,
) -> None:
    """Read a chart-generation payload and atomically publish an evening manifest."""
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid chart-generation manifest: {source_path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"chart-generation manifest must be an object: {source_path}")

    review_payload = None
    if review_path is not None:
        try:
            review_payload = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid evening review: {review_path}: {exc}") from exc
        if not isinstance(review_payload, Mapping):
            raise ValueError(f"evening review must be an object: {review_path}")
    manifest = build_evening_manifest(
        payload, expected_date=expected_date, review_payload=review_payload
    )
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
    parser.add_argument("--review-json", type=Path)
    args = parser.parse_args()
    write_evening_manifest(
        args.source, args.output, expected_date=args.date, review_path=args.review_json
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
