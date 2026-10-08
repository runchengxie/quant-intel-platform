"""Bounded source capture and six-section private preview CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import requests

from .news_snapshot_parse import MAX_BYTES, SOURCE_URL, parse_snapshot
from .news_snapshot_preview import render_preview


def _output_path(path: Path) -> Path:
    resolved = path.resolve()
    markers = (parent / ".git" for parent in (resolved, *resolved.parents))
    if any(marker.is_file() or (marker / "HEAD").is_file() for marker in markers):
        raise ValueError("output must be outside source repositories")
    if resolved.exists():
        raise FileExistsError("snapshot destination already exists")
    return resolved


@dataclass(frozen=True)
class CaptureOptions:
    mode: str = "replay"
    locale: str = "en-US"
    editorial: dict[str, Any] | None = None


def capture(
    raw: bytes,
    *,
    expected_date: date,
    captured_at: datetime,
    output_dir: Path,
    options: CaptureOptions | None = None,
) -> dict[str, Any]:
    options = options or CaptureOptions()
    destination = _output_path(output_dir)
    snapshot = parse_snapshot(raw, expected_date, captured_at, options.mode)
    editorial = options.editorial
    preview = render_preview(snapshot, locale=options.locale, editorial=editorial)
    destination.mkdir(parents=True, mode=0o700)
    # A unique directory owns the bundle; no existing run is overwritten.
    (destination / "source.xml").write_bytes(raw)
    (destination / "snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "preview.md").write_text(preview, encoding="utf-8")
    if editorial is not None:
        (destination / "editorial.json").write_text(
            json.dumps(editorial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in destination.iterdir()
        if path.is_file()
    }
    (destination / "receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "market.news-snapshot-receipt.v1",
                "files": hashes,
                "status": snapshot["status"],
                "review_status": "needs_review",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return snapshot


def fetch_source() -> bytes:
    with requests.get(SOURCE_URL, timeout=(10, 30), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("unexpected feed response status")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise ValueError("source exceeds 1 MiB")
        return bytes(content)


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("capture timestamp requires timezone")
    if parsed > datetime.now(UTC):
        raise ValueError("capture timestamp is in the future")
    return parsed


def _expected_date(value: str) -> date:
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError("expected date must use YYYY-MM-DD")
    return result


def _editorial(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        text = stream.read(65537)
    if len(text) > 65536:
        raise ValueError("editorial exceeds 64 KiB")
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("editorial must be an object")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture StreetAccount source and an unreviewed six-section preview"
    )
    parser.add_argument("--date", required=True, help="Expected US trading date, YYYY-MM-DD")
    parser.add_argument(
        "--output-dir", required=True, type=Path, help="New directory outside source repositories"
    )
    parser.add_argument(
        "--input-rss", type=Path, help="Replay bounded frozen RSS instead of fetching"
    )
    parser.add_argument(
        "--captured-at", help="Original timezone-aware capture time; required for replay"
    )
    parser.add_argument("--locale", choices=("en-US", "zh-CN"), default="en-US")
    parser.add_argument(
        "--editor-json", type=Path, help="Optional hash-bound editorial text; never approval"
    )
    args = parser.parse_args(argv)
    if bool(args.input_rss) != bool(args.captured_at):
        parser.error("--input-rss and --captured-at must be provided together")
    try:
        expected = _expected_date(args.date)
        _output_path(args.output_dir)
        if args.input_rss:
            with args.input_rss.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            captured = _aware(args.captured_at)
        else:
            raw, captured = fetch_source(), datetime.now(UTC)
        editorial = _editorial(args.editor_json) if args.editor_json else None
        result = capture(
            raw,
            expected_date=expected,
            captured_at=captured,
            output_dir=args.output_dir,
            options=CaptureOptions(
                mode="replay" if args.input_rss else "live",
                locale=args.locale,
                editorial=editorial,
            ),
        )
    except (ValueError, OSError, requests.RequestException) as exc:
        parser.exit(1, f"Source capture failed: {type(exc).__name__}\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "issues": result["issues"],
                "output_dir": str(args.output_dir),
            }
        )
    )
    return 2 if result["status"] == "quarantined" else 0


if __name__ == "__main__":
    raise SystemExit(main())
