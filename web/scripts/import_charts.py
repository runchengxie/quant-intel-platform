"""Preview or atomically import one independently reviewed public chart file."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

try:
    from .chart_contract import validate_public_chart
    from .chart_review import validate_review_receipt
    from .public_paths import public_snapshot_root
except ImportError:
    from chart_contract import validate_public_chart
    from chart_review import validate_review_receipt
    from public_paths import public_snapshot_root


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _archive_review(archive: Path, report_id: str, chart_hash: str, review: dict) -> bool:
    canonical = json.dumps(review, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    review_sha256 = hashlib.sha256(canonical).hexdigest()
    path = archive / "chart_reviews" / report_id / chart_hash / f"{review_sha256}.json"
    if path.exists():
        return False
    _write_atomic(path, (json.dumps(review, ensure_ascii=False, indent=2) + "\n").encode())
    return True


def import_charts(
    root: Path, source: Path, archive: Path, *, review: Path | None = None, apply: bool = False
) -> dict:
    """Require a public manifest and an indexed report; never promote candidates."""
    root, source, archive = root.resolve(), source.resolve(), archive.resolve()
    if archive.is_relative_to(root) or root.is_relative_to(archive):
        raise ValueError("chart archive must be outside public repository")
    payload = validate_public_chart(json.loads(source.read_text(encoding="utf-8")))
    if review is None:
        raise ValueError("private review receipt is required")
    review = review.resolve()
    if review.is_relative_to(root):
        raise ValueError("review receipt must remain outside public repository")
    reviewed = validate_review_receipt(payload, json.loads(review.read_text(encoding="utf-8")))
    report_id = payload["report_id"]
    public_root = public_snapshot_root(root)
    index = json.loads((public_root / "data/reports.json").read_text(encoding="utf-8"))
    if index.get("schema_version") != "market_intel_pages.reports.v1" or not isinstance(
        index.get("reports"), list
    ):
        raise ValueError("invalid report index")
    if report_id not in {item.get("id") for item in index["reports"] if isinstance(item, dict)}:
        raise ValueError("chart identity is not in the public report index")
    destination = public_root / "data" / "charts" / f"{report_id}.json"
    old = destination.read_bytes() if destination.is_file() else None
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    changed = int(old != data)
    result = {"changed": changed, "report_id": report_id, "applied": False}
    if not apply:
        return result
    review_archived = _archive_review(archive, report_id, payload["content_sha256"], reviewed)
    if not changed:
        return {**result, "review_archived": review_archived}
    if old is not None:
        old_payload = validate_public_chart(json.loads(old))
        old_hash = old_payload["content_sha256"]
        archive_path = archive / "chart_revisions" / report_id / f"{old_hash}.json"
        if not archive_path.exists():
            _write_atomic(archive_path, old)
    _write_atomic(destination, data)
    return {**result, "applied": True, "review_archived": review_archived}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path, help="Private point-level review receipt")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            import_charts(args.root, args.source, args.archive, review=args.review, apply=args.apply),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
