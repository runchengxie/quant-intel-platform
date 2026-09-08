from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILE_RECEIPT_SCHEMA_VERSION = "research.file-receipts.v1"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class FileReceipt:
    path: str
    sha256: str
    size: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> FileReceipt:
        path = str(payload.get("path", "")).strip()
        sha256 = str(payload.get("sha256", "")).strip()
        size = int(payload.get("size", -1))
        if not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("file receipt path must be a safe relative path")
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
            raise ValueError(f"invalid SHA-256 for {path}")
        if size < 0:
            raise ValueError(f"invalid file size for {path}")
        return cls(path=path, sha256=sha256, size=size)

    def to_mapping(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


def build_file_receipts(root: Path, paths: Iterable[Path]) -> tuple[FileReceipt, ...]:
    resolved_root = root.resolve()
    receipts: list[FileReceipt] = []
    for path in sorted((item.resolve() for item in paths), key=str):
        if resolved_root not in path.parents:
            raise ValueError(f"artifact file escapes root: {path}")
        if not path.is_file():
            raise ValueError(f"artifact file is missing: {path}")
        receipts.append(
            FileReceipt(
                path=path.relative_to(resolved_root).as_posix(),
                sha256=file_sha256(path),
                size=path.stat().st_size,
            )
        )
    return tuple(receipts)


def file_receipt_payload(receipts: Iterable[FileReceipt]) -> dict[str, object]:
    records = [receipt.to_mapping() for receipt in receipts]
    return {
        "schema_version": FILE_RECEIPT_SCHEMA_VERSION,
        "files": records,
        "inventory_sha256": canonical_json_sha256(records),
    }


def _parse_receipts(payload: Mapping[str, Any]) -> tuple[FileReceipt, ...]:
    if payload.get("schema_version") != FILE_RECEIPT_SCHEMA_VERSION:
        raise ValueError("unsupported file receipt schema")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("file receipt inventory must be a non-empty list")
    receipts = tuple(
        FileReceipt.from_mapping(item) for item in raw_files if isinstance(item, Mapping)
    )
    if len(receipts) != len(raw_files):
        raise ValueError("each file receipt must be an object")
    records = [receipt.to_mapping() for receipt in receipts]
    if payload.get("inventory_sha256") != canonical_json_sha256(records):
        raise ValueError("file receipt inventory SHA-256 mismatch")
    return receipts


def _validate_receipt_file(root: Path, receipt: FileReceipt) -> None:
    path = (root / receipt.path).resolve()
    if root not in path.parents:
        raise ValueError(f"artifact file escapes root: {receipt.path}")
    if not path.is_file():
        raise ValueError(f"artifact file is missing: {receipt.path}")
    if path.stat().st_size != receipt.size:
        raise ValueError(f"artifact file size mismatch: {receipt.path}")
    if file_sha256(path) != receipt.sha256:
        raise ValueError(f"artifact file SHA-256 mismatch: {receipt.path}")


def validate_file_receipts(
    root: Path,
    payload: Mapping[str, Any],
    *,
    required_files: Iterable[str] = (),
) -> tuple[FileReceipt, ...]:
    receipts = _parse_receipts(payload)
    names = {receipt.path for receipt in receipts}
    missing = sorted(set(required_files) - names)
    if missing:
        raise ValueError("missing required artifact files: " + ", ".join(missing))

    resolved_root = root.resolve()
    for receipt in receipts:
        _validate_receipt_file(resolved_root, receipt)
    return receipts
