"""Bind a private, point-level fact and rights review to a public chart artifact.

This checks review completeness and identity, not the truth of reviewer attestations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    from .chart_contract import _source_url, _text, validate_public_chart
except ImportError:
    from chart_contract import _source_url, _text, validate_public_chart

SCHEMA = "market_intel_pages.chart_review.v1"
POINT_FIELDS = {"chart_key", "point_sha256", "fact_url", "fact_note", "rights_url", "rights_note"}


def _point_hash(chart_key: str, point: dict) -> str:
    canonical = json.dumps(
        {"chart_key": chart_key, "point": point},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def make_review_template(chart: object) -> dict:
    """List every public point; blank fields deliberately fail review validation."""
    payload = validate_public_chart(chart)
    return {
        "schema_version": SCHEMA,
        "report_id": payload["report_id"],
        "chart_sha256": payload["content_sha256"],
        "reviewer": "",
        "reviewed_at": "",
        "points": [
            {
                "chart_key": card["key"],
                "point_sha256": _point_hash(card["key"], point),
                "fact_url": "",
                "fact_note": "",
                "rights_url": "",
                "rights_note": "",
            }
            for card in payload["charts"]
            for point in card["points"]
        ],
    }


def _validate_review_points(payload: dict, points: object) -> None:
    expected = Counter(
        (card["key"], _point_hash(card["key"], point))
        for card in payload["charts"]
        for point in card["points"]
    )
    if not isinstance(points, list):
        raise ValueError("review points must be a list")
    actual: Counter[tuple[str, str]] = Counter()
    for point in points:
        if not isinstance(point, dict) or set(point) != POINT_FIELDS:
            raise ValueError("review point field mismatch")
        actual[(point["chart_key"], point["point_sha256"])] += 1
        for field in ("fact_url", "rights_url"):
            try:
                _source_url(point[field])
            except ValueError as exc:
                raise ValueError(f"{field}: {exc}") from exc
        for field in ("fact_note", "rights_note"):
            _text(point[field], field)
    if actual != expected:
        raise ValueError("review points do not cover every chart point exactly once")


def validate_review_receipt(chart: object, review: object) -> dict:
    """Require a dated, full-coverage private review for exact canonical chart content."""
    payload = validate_public_chart(chart)
    if not isinstance(review, dict) or set(review) != {
        "schema_version",
        "report_id",
        "chart_sha256",
        "reviewer",
        "reviewed_at",
        "points",
    }:
        raise ValueError("review receipt field mismatch")
    if review["schema_version"] != SCHEMA or review["report_id"] != payload["report_id"]:
        raise ValueError("review receipt identity mismatch")
    if review["chart_sha256"] != payload["content_sha256"]:
        raise ValueError("review receipt chart hash mismatch")
    _text(review["reviewer"], "reviewer")
    try:
        reviewed_at = datetime.fromisoformat(review["reviewed_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("reviewed_at needs timezone") from exc
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("reviewed_at needs timezone")
    if reviewed_at < datetime.fromisoformat(payload["generated_at"]):
        raise ValueError("reviewed_at precedes chart generation")
    _validate_review_points(payload, review["points"])
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Reviewed public chart JSON")
    parser.add_argument("--output", required=True, type=Path, help="Private receipt template path")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("private review template must remain outside public repository")
    if output.exists():
        raise ValueError("review template output already exists")
    template = make_review_template(json.loads(args.source.read_text(encoding="utf-8")))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report_id": template["report_id"], "points": len(template["points"])}))


if __name__ == "__main__":
    main()
