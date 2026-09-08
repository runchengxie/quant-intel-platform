"""Consume the versioned style-factor artifact produced by research-workspace.

This command deliberately contains no factor calculation or backtest logic. The owner
workflow publishes a complete report, charts, daily factor returns, manifest, SHA-256
inventory, and lineage under ``DATA_PLATFORM_ROOT/strategy_outputs/style-factors``.
market-intel validates and stages that immutable artifact for report delivery.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_contracts import (
    ArtifactEnvelopeV2,
    file_sha256,
    read_artifact_envelope,
    validate_file_receipts,
)

STYLE_ARTIFACT_SCHEMA_VERSION = "research.style-factors.v1"
REQUIRED_STYLE_FILES = (
    "factor_summary.json",
    "factor_correlation.json",
    "factor_yearly.csv",
    "style_analysis_report.md",
    "style_factor_nav.png",
    "style_factor_comparison.png",
    "style_factor_corr.png",
    "style_factor_yearly.png",
    "meta.json",
)


@dataclass(frozen=True)
class StyleArtifact:
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]
    envelope: ArtifactEnvelopeV2


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def resolve_style_artifact(data_root: Path, version: str | None = None) -> StyleArtifact:
    output_base = data_root.expanduser().resolve() / "strategy_outputs" / "style-factors"
    resolved_version = str(version or "").strip()
    if not resolved_version:
        latest_path = output_base / "latest.txt"
        if not latest_path.is_file():
            raise FileNotFoundError(f"style-factor latest pointer is missing: {latest_path}")
        resolved_version = latest_path.read_text(encoding="utf-8").strip()
    if not resolved_version or Path(resolved_version).name != resolved_version:
        raise ValueError("style-factor version must be one safe directory name")

    root = (output_base / resolved_version).resolve()
    if output_base.resolve() not in root.parents:
        raise ValueError("style-factor version escapes the artifact root")
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != STYLE_ARTIFACT_SCHEMA_VERSION:
        raise ValueError("unsupported style-factor artifact schema")
    envelope = read_artifact_envelope(manifest, allow_legacy=False)
    if not isinstance(envelope, ArtifactEnvelopeV2):
        raise ValueError("style-factor artifact requires an envelope v2")
    if envelope.artifact_type != "style_factor_analysis":
        raise ValueError("unexpected style-factor artifact type")
    receipt_payload = manifest.get("file_receipts")
    if not isinstance(receipt_payload, dict):
        raise ValueError("style-factor artifact requires file_receipts")
    receipts = validate_file_receipts(
        root,
        receipt_payload,
        required_files=REQUIRED_STYLE_FILES,
    )
    if envelope.content_sha256 != receipt_payload.get("inventory_sha256"):
        raise ValueError("style-factor envelope does not bind the file inventory")
    if "manifest.json" in {receipt.path for receipt in receipts}:
        raise ValueError("manifest.json must not recursively receipt itself")
    return StyleArtifact(
        root=root,
        manifest_path=manifest_path,
        manifest=manifest,
        envelope=envelope,
    )


def consume_style_artifact(
    artifact: StyleArtifact,
    outdir: Path,
    *,
    force: bool = False,
) -> Path:
    destination = outdir.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise FileExistsError(f"output already exists; pass --force to replace it: {destination}")
    if destination.exists():
        prior_receipt = destination / "consumption_receipt.json"
        try:
            prior_payload = _read_json(prior_receipt)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"refusing to replace an unrecognized output directory: {destination}"
            ) from exc
        if prior_payload.get("schema_version") != "market-intel.style-factor-consumption.v1":
            raise ValueError(f"refusing to replace an unrecognized output directory: {destination}")

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        receipt_payload = artifact.manifest["file_receipts"]
        for receipt in receipt_payload["files"]:
            relative = Path(str(receipt["path"]))
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(artifact.root / relative, target)
        shutil.copy2(artifact.manifest_path, staging / "manifest.json")
        consumption_receipt = {
            "schema_version": "market-intel.style-factor-consumption.v1",
            "consumed_at": datetime.now(UTC).isoformat(),
            "source_artifact_id": artifact.envelope.artifact_id,
            "source_run_id": artifact.envelope.run_id,
            "source_manifest_sha256": file_sha256(artifact.manifest_path),
            "source_producer": artifact.envelope.producer.to_mapping(),
        }
        (staging / "consumption_receipt.json").write_text(
            json.dumps(consumption_receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            shutil.rmtree(destination)
        staging.replace(destination)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        default=os.environ.get("DATA_PLATFORM_ROOT"),
        help="market-data-platform shared data root (or DATA_PLATFORM_ROOT)",
    )
    parser.add_argument("--version", help="immutable style-factor version; defaults to latest.txt")
    parser.add_argument("--outdir", default="artifacts/style_analysis")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--strategy-csv",
        help="unsupported here; run the research-workspace publisher with this option",
    )
    parser.add_argument("--strategy-name", default="strategy")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="unsupported here; quick/full is selected by the owner publisher",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.data_root:
        raise SystemExit("DATA_PLATFORM_ROOT or --data-root is required")
    if args.strategy_csv or args.quick:
        raise SystemExit(
            "style_analysis is now a read-only artifact consumer. "
            "Run research-workspace's style_factor_attribution publisher for recomputation."
        )
    artifact = resolve_style_artifact(Path(args.data_root), args.version)
    destination = consume_style_artifact(artifact, Path(args.outdir), force=args.force)
    print(f"[OK] consumed {artifact.envelope.artifact_id} from {artifact.root} -> {destination}")


if __name__ == "__main__":
    main()
