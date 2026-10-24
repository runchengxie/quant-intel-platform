"""Export and import explicit-public, hash-bound weekly recap bundles."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from a_share_analysis.weekly_analysis_artifact import validate_weekly_analysis_artifact
from market_intel_publication.public_paths import public_snapshot_root
from market_intel_publication.weekly_recap_contract import (
    INDEX_SCHEMA,
    SCHEMA,
    content_hash,
    exact,
    iso_date,
    validate_weekly_recap,
)


def read_file(path: Path, limit: int = 20_000_000) -> bytes:
    """Read bounded regular files, rejecting symlink ancestors."""
    if (
        any(parent.is_symlink() for parent in (path, *path.parents))
        or not path.is_file()
        or path.stat().st_size > limit
    ):
        raise ValueError("unsafe or oversized weekly input")
    return path.read_bytes()


def read_json(path: Path) -> dict:
    return json.loads(read_file(path, 5_000_000))


def image_metadata(raw: bytes) -> dict:
    with Image.open(io.BytesIO(raw)) as image:
        if (
            image.format != "PNG"
            or not 1 <= image.width <= 20000
            or not 1 <= image.height <= 20000
            or image.width * image.height > 40_000_000
        ):
            raise ValueError("weekly image must be a bounded PNG")
        dimensions = {"width": image.width, "height": image.height}
        image.verify()
    return {**dimensions, "sha256": hashlib.sha256(raw).hexdigest()}


def _owner(path: Path, kind: str, day: str) -> tuple[dict, dict]:
    raw = read_file(path)
    artifact = validate_weekly_analysis_artifact(
        json.loads(raw), artifact_type=f"{kind}_weekly", expected_as_of=day
    )
    return artifact, {
        "schema_version": artifact["schema_version"],
        "as_of": day,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _day(value: str) -> str:
    return iso_date(datetime.strptime(value.replace("-", ""), "%Y%m%d").date().isoformat())


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def _replace(staged: Path, output: Path, backup: Path) -> None:
    if output.exists():
        output.replace(backup)
    try:
        staged.replace(output)
    except OSError:
        if backup.exists():
            backup.replace(output)
        raise


@dataclass(frozen=True)
class WeeklyInputs:
    """Explicit input paths; none are disclosed in the public projection."""

    report: Path
    image: Path
    value_artifact: Path
    size_artifact: Path


def export_bundle(inputs: WeeklyInputs, day: str, output: Path, publication: str) -> dict:
    """Project admitted owner facts only; never publish the raw artifacts."""
    if publication != "public":
        raise ValueError("explicit publication public is required")
    iso_date(day)
    report, image = inputs.report, inputs.image
    value_artifact, size_artifact = inputs.value_artifact, inputs.size_artifact
    value, value_source = _owner(value_artifact, "value_regime", day)
    size, size_source = _owner(size_artifact, "size_style", day)
    markdown = read_file(report, 1_000_000).decode("utf-8")
    png = read_file(image)
    value_rows = [
        {
            "date": _day(r["date"]),
            "return_12w_percent": r["ret_12w"] * 100,
            "wealth_index": r["cum"],
        }
        for r in value["weekly_features"][-104:]
    ]
    size_rows = [
        {
            "date": _day(r["date"]),
            "relative_strength": r["relative_strength"],
            "small_crowding": r["small"],
            "large_crowding": r["large"],
        }
        for r in size["series"][-252:]
    ]
    payload = {
        "schema_version": SCHEMA,
        "publication": publication,
        "report_id": f"{day}-weekly",
        "date": day,
        "generated_at": datetime.now(UTC).isoformat(),
        "markdown": markdown,
        "source_url": f"reports/{day}-weekly.md",
        "image": {"source_url": f"reports/{day}-weekly.png", **image_metadata(png)},
        "summary": {
            "value_regime": value["snapshot"]["regime"],
            "value_streak_weeks": value["snapshot"]["streak"],
            "value_return_12w_percent": value_rows[-1]["return_12w_percent"],
            "small_crowding": size_rows[-1]["small_crowding"],
            "large_crowding": size_rows[-1]["large_crowding"],
            "size_signal": size["snapshot"]["signal"],
        },
        "series": {"value": value_rows, "size": size_rows},
        "sources": {"value": value_source, "size": size_source},
    }
    payload["content_hash"] = content_hash(payload)
    validate_weekly_recap(payload)
    output = _safe_destination(output, [report, image, value_artifact, size_artifact])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="weekly-export-", dir=output.parent) as temporary:
        stage = Path(temporary) / "new"
        stage.mkdir()
        _write_json(stage / "weekly_recap.json", payload)
        (stage / f"{day}-weekly.md").write_bytes(markdown.encode())
        (stage / f"{day}-weekly.png").write_bytes(png)
        load_bundle(stage)
        _replace(stage, output, Path(temporary) / "previous")
    return payload


def _safe_destination(output: Path, inputs: list[Path]) -> Path:
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError("unsafe weekly destination")
    output = output.resolve()
    if output == output.parent or any(p.resolve().is_relative_to(output) for p in inputs):
        raise ValueError("weekly destination contains input")
    return output


def load_bundle(bundle: Path) -> dict:
    payload = validate_weekly_recap(read_json(bundle / "weekly_recap.json"))
    day = payload["date"]
    if {p.name for p in bundle.iterdir()} != {
        "weekly_recap.json",
        f"{day}-weekly.md",
        f"{day}-weekly.png",
    }:
        raise ValueError("weekly bundle contains unexpected files")
    _validate_files(payload, bundle / f"{day}-weekly.md", bundle / f"{day}-weekly.png")
    return payload


def _validate_files(payload: dict, markdown: Path, image: Path) -> None:
    if read_file(markdown, 1_000_000).decode("utf-8") != payload["markdown"]:
        raise ValueError("weekly Markdown mismatch")
    metadata = image_metadata(read_file(image))
    if metadata != {k: payload["image"][k] for k in ("width", "height", "sha256")}:
        raise ValueError("weekly image hash or dimensions mismatch")


def weekly_history(public: Path) -> list[dict]:
    index = public / "data/weekly_recaps.json"
    latest = public / "data/weekly_recap.json"
    if not index.exists() and not latest.exists():
        return []
    raw = exact(read_json(index), "schema_version reports")
    if (
        raw["schema_version"] != INDEX_SCHEMA
        or not isinstance(raw["reports"], list)
        or not 1 <= len(raw["reports"]) <= 5
    ):
        raise ValueError("invalid weekly index")
    rows = [validate_weekly_recap(row) for row in raw["reports"]]
    dates = [row["date"] for row in rows]
    if dates != sorted(set(dates), reverse=True) or read_json(latest) != rows[0]:
        raise ValueError("weekly latest/index mismatch")
    for row in rows:
        _validate_files(row, public / row["source_url"], public / row["image"]["source_url"])
    return rows


def copy_weekly(public: Path, output: Path) -> None:
    """Snapshot only validated, indexed weekly files."""
    rows = weekly_history(public)
    if not rows:
        return
    _write_json(output / "data/weekly_recap.json", rows[0])
    _write_json(
        output / "data/weekly_recaps.json", {"schema_version": INDEX_SCHEMA, "reports": rows}
    )
    for row in rows:
        for source in (row["source_url"], row["image"]["source_url"]):
            target = output / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_file(public / source))
    weekly_history(output)


def import_bundle(bundle: Path, root: Path, dry_run: bool = False) -> dict:
    """Validate before atomically replacing the complete public directory."""
    payload = load_bundle(bundle)
    public = public_snapshot_root(root)
    _safe_destination(public, [bundle])
    rows = weekly_history(public)
    if rows and payload["date"] < rows[0]["date"]:
        raise ValueError("stale weekly import")
    by_date = {row["date"]: row for row in rows}
    by_date[payload["date"]] = payload
    retained = sorted(by_date.values(), key=lambda row: row["date"], reverse=True)[:5]
    if dry_run:
        return payload
    public.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="weekly-import-", dir=public.parent) as temporary:
        stage = Path(temporary) / "new"
        if public.exists():
            shutil.copytree(public, stage, symlinks=True)
        else:
            stage.mkdir()
        for row in rows:
            if row not in retained:
                for source in (row["source_url"], row["image"]["source_url"]):
                    (stage / source).unlink()
        for source in (payload["source_url"], payload["image"]["source_url"]):
            target = stage / source
            target.parent.mkdir(parents=True, exist_ok=True)
            if any(p.is_symlink() for p in (target, *target.parents)):
                raise ValueError("unsafe weekly destination")
            target.write_bytes(read_file(bundle / Path(source).name))
        for name, obj in (
            ("weekly_recap.json", retained[0]),
            ("weekly_recaps.json", {"schema_version": INDEX_SCHEMA, "reports": retained}),
        ):
            target = stage / "data" / name
            if any(p.is_symlink() for p in (target, *target.parents)):
                raise ValueError("unsafe weekly destination")
            _write_json(target, obj)
        weekly_history(stage)
        _replace(stage, public, Path(temporary) / "previous")
    return payload


def export_main() -> None:
    parser = argparse.ArgumentParser(description="Export an explicit-public weekly recap bundle")
    for name in ("report", "image", "value-artifact", "size-artifact", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--publication", choices=["public"], required=True)
    args = parser.parse_args()
    export_bundle(
        WeeklyInputs(args.report, args.image, args.value_artifact, args.size_artifact),
        args.date,
        args.output,
        args.publication,
    )


def import_main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and atomically import a public weekly recap"
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    import_bundle(args.bundle, args.root, args.dry_run)
