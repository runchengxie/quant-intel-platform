"""Deterministic public snapshot packaging and bounded transactional verification."""

from __future__ import annotations

import io
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path

from market_intel_publication import site_content_contract as contract
from market_intel_publication.export_site_snapshot import export_site_snapshot
from market_intel_publication.pipeline_health import health_report
from market_intel_publication.site_content_contract import (
    ContentBundleReceipt,
    installed_producer,
)
from market_intel_publication.site_content_validation import validate_public_snapshot


def new_output(output: Path, inputs: tuple[Path, ...]) -> Path:
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("symlinked output path")
    resolved = output.resolve()
    if resolved.exists() or any(
        resolved == source.resolve()
        or resolved.is_relative_to(source.resolve())
        or source.resolve().is_relative_to(resolved)
        for source in inputs
    ):
        raise ValueError("output must be new and must not overlap inputs")
    return resolved


def _archive(manifest: dict, payload: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        entries = {"manifest.json": contract.canonical(manifest)}
        entries.update({f"payload/{name}": raw for name, raw in sorted(payload.items())})
        for name, raw in entries.items():
            info = zipfile.ZipInfo(name, date_time=contract.ZIP_TIME)
            info.create_system = 3
            info.external_attr = contract.ZIP_MODE
            archive.writestr(info, raw)
    raw = stream.getvalue()
    if len(raw) > contract.MAX_ARCHIVE_BYTES:
        raise ValueError("archive size limit exceeded")
    return raw


def _manifest(payload: dict[str, bytes], created_at: str, producer: dict) -> dict:
    result = {
        "schema_version": contract.SCHEMA,
        "publication": "public",
        "created_at_utc": created_at,
        "producer": producer,
        "files": [
            {"path": name, "sha256": contract.digest(raw), "bytes": len(raw)}
            for name, raw in sorted(payload.items())
        ],
    }
    result["bundle_id"] = contract.digest(contract.canonical(result))
    contract.manifest_files(result, producer)
    if len(contract.canonical(result)) > contract.MAX_MANIFEST_BYTES:
        raise ValueError("manifest size limit exceeded")
    return result


def _receipt(manifest: dict, raw: bytes, producer: dict) -> ContentBundleReceipt:
    return ContentBundleReceipt(
        schema_version=contract.RECEIPT_SCHEMA,
        bundle_id=manifest["bundle_id"],
        archive_sha256=contract.digest(raw),
        producer_revision=producer["source_revision"],
        created_at_utc=manifest["created_at_utc"],
        files=contract.manifest_files(manifest, producer),
    )


def pack_site_content(
    root: Path, output: Path, *, created_at_utc: str, producer_revision: str
) -> ContentBundleReceipt:
    """Export eligible indexed families and create a new deterministic public archive."""
    output = new_output(output, (root,))
    created = contract.utc_time(created_at_utc)
    producer = installed_producer(producer_revision)
    validate_public_snapshot(root / "artifacts/public", strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".site-content-", dir=output.parent) as temporary:
        snapshot = Path(temporary) / "snapshot"
        export_site_snapshot(root, snapshot)
        # Only this new transport fixes the clock; legacy renderer semantics remain.
        report_index = contract.read_json((snapshot / "data/reports.json").read_bytes())
        (snapshot / "data/health.json").write_bytes(
            contract.canonical(health_report(report_index, now=created))
        )
        names = validate_public_snapshot(snapshot, created_at_utc=created_at_utc)
        payload = {name: contract.source_file(snapshot / name, snapshot) for name in names}
        manifest = _manifest(payload, created_at_utc, producer)
        raw = _archive(manifest, payload)
        receipt = _receipt(manifest, raw, producer)
        staged = Path(temporary) / "bundle.zip"
        staged.write_bytes(raw)
        # Hard-link promotion is exclusive: concurrent callers cannot replace output.
        output.hardlink_to(staged)
    return receipt


def _member(info: zipfile.ZipInfo) -> None:
    if (
        info.date_time != contract.ZIP_TIME
        or info.create_system != 3
        or info.external_attr != contract.ZIP_MODE
        or info.compress_type != zipfile.ZIP_STORED
        or info.flag_bits
        or info.extra
        or info.comment
        or info.is_dir()
        or info.file_size != info.compress_size
    ):
        raise ValueError("unsupported ZIP member metadata")


def _read_archive(raw: bytes, producer: dict) -> tuple[dict, dict[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if not 2 <= len(infos) <= contract.MAX_FILES + 1:
            raise ValueError("ZIP member count limit exceeded")
        names = [info.filename for info in infos]
        if names[0] != "manifest.json" or len(names) != len(set(names)):
            raise ValueError("missing manifest or duplicate ZIP member")
        for info in infos:
            _member(info)
            limit = (
                contract.MAX_MANIFEST_BYTES
                if info.filename == "manifest.json"
                else contract.MAX_FILE_BYTES
            )
            if info.file_size > limit:
                raise ValueError("ZIP member size limit exceeded")
        if sum(info.file_size for info in infos[1:]) > contract.MAX_EXPANDED_BYTES:
            raise ValueError("expanded ZIP size limit exceeded")
        manifest = contract.read_json(archive.read(infos[0]))
        records = contract.manifest_files(manifest, producer)
        if names != ["manifest.json", *[f"payload/{row.path}" for row in records]]:
            raise ValueError("unindexed or reordered ZIP members")
        payload = {}
        for row in records:
            raw_file = archive.read(f"payload/{row.path}")
            if len(raw_file) != row.bytes or contract.digest(raw_file) != row.sha256:
                raise ValueError("payload size or digest mismatch")
            payload[row.path] = raw_file
    if _archive(manifest, payload) != raw:
        raise ValueError("noncanonical ZIP or manifest bytes")
    return manifest, payload


def verify_site_content(
    bundle: Path, expected_sha256: str, output: Path, *, expected_producer_revision: str
) -> ContentBundleReceipt:
    """Verify exact bytes and eligibility before promoting a new wrapped input root."""
    output = new_output(output, (bundle,))
    contract.hex_digest(expected_sha256)
    raw = contract.source_file(bundle, bundle.parent, contract.MAX_ARCHIVE_BYTES)
    if contract.digest(raw) != expected_sha256:
        raise ValueError("archive digest mismatch")
    producer = installed_producer(expected_producer_revision)
    try:
        manifest, payload = _read_archive(raw, producer)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError("invalid or unsupported ZIP archive") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".site-content-", dir=output.parent) as temporary:
        staged = Path(temporary) / "verified"
        public = staged / "artifacts/public"
        for name, content in payload.items():
            target = public / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        validate_public_snapshot(public, created_at_utc=manifest["created_at_utc"])
        receipt = _receipt(manifest, raw, producer)
        new_output(output, (bundle,))
        staged.rename(output)
    return receipt


def receipt_bytes(receipt: ContentBundleReceipt) -> bytes:
    return contract.canonical(asdict(receipt)) + b"\n"
