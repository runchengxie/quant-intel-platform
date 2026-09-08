"""Validate and atomically promote staged report datasets."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml


class PromotionValidationError(RuntimeError):
    """Raised when a staged mirror cannot safely replace current data."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _date_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise PromotionValidationError("manifest_missing", f"staged manifest is missing: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PromotionValidationError(
            "manifest_invalid", f"failed to read staged manifest {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise PromotionValidationError(
            "manifest_invalid", f"staged manifest is not a mapping: {path}"
        )
    return payload


def _partition_path(root: Path, trade_date: str) -> Path:
    return root / "data" / f"trade_date={trade_date}" / "part.parquet"


def _require_nonempty_partition(path: Path, *, trade_date: str) -> int:
    if not path.is_file() or path.stat().st_size <= 0:
        raise PromotionValidationError(
            "partition_invalid",
            f"staged partition for {trade_date} is missing or empty: {path}",
        )
    try:
        metadata = pq.ParquetFile(path).metadata
    except Exception as exc:
        raise PromotionValidationError(
            "partition_invalid",
            f"staged partition for {trade_date} is not readable parquet: {path}: {exc}",
        ) from exc
    if metadata.num_rows <= 0:
        raise PromotionValidationError(
            "partition_invalid",
            f"staged partition for {trade_date} contains no rows: {path}",
        )
    return metadata.num_rows


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _dc_receipt_matches_partition(receipt: object, partition: Path, trade_date: str) -> bool:
    if not isinstance(receipt, dict) or receipt.get("complete") is not True:
        return False
    row_count = receipt.get("row_count")
    page_count = receipt.get("page_count")
    distinct_theme_count = receipt.get("distinct_theme_count")
    coverage = receipt.get("coverage")
    if (
        not _is_positive_int(row_count)
        or not _is_positive_int(page_count)
        or receipt.get("terminal_page_reached") is not True
        or not _is_positive_int(distinct_theme_count)
        or not isinstance(coverage, dict)
        or coverage.get("field") != "theme_code"
        or type(coverage.get("populated_row_count")) is not int
        or coverage.get("populated_row_count") != row_count
        or type(coverage.get("row_coverage_ratio")) not in {int, float}
        or coverage.get("row_coverage_ratio") != 1.0
    ):
        return False
    try:
        return _require_nonempty_partition(partition, trade_date=trade_date) == row_count
    except PromotionValidationError:
        return False


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_manifest_temp(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
        handle.flush()
        os.fsync(handle.fileno())


def _sanitize_dc_promotion_manifest(
    manifest: dict[str, Any], promoted_dates: Sequence[str]
) -> list[str]:
    completeness = manifest.get("completeness")
    if not isinstance(completeness, dict):
        return []
    receipts = completeness.get("trade_dates")
    if not isinstance(receipts, dict):
        return []

    promoted = list(dict.fromkeys(str(day) for day in promoted_dates))
    promoted_set = set(promoted)
    observed = [
        *[str(day) for day in receipts],
        *_date_list(manifest.get("written_trade_dates")),
        *_date_list(manifest.get("empty_trade_dates")),
        *_date_list(manifest.get("skipped_trade_dates")),
    ]
    unpromoted = [day for day in dict.fromkeys(observed) if day and day not in promoted_set]
    for trade_date in unpromoted:
        receipt = receipts.get(trade_date)
        if not isinstance(receipt, dict):
            receipt = {"trade_date": trade_date}
        receipts[trade_date] = {
            **receipt,
            "trade_date": trade_date,
            "complete": False,
            "source": "staged_unpromoted_receipt",
        }

    is_complete = bool(promoted) and not unpromoted
    manifest["complete"] = is_complete
    completeness.update(
        {
            "complete": is_complete,
            "complete_trade_dates": promoted,
            "incomplete_trade_dates": unpromoted,
            "trade_dates": receipts,
        }
    )
    totals = manifest.get("totals")
    if isinstance(totals, dict):
        totals["complete_trade_dates"] = len(promoted)
        totals["incomplete_trade_dates"] = len(unpromoted)
    return unpromoted


def _manifest_replacement(
    manifest: dict[str, Any],
    *,
    destination_dir: Path,
    run_id: str,
    target_receipt_valid: bool,
    negative_reason: str | None = None,
    promoted_dates: Sequence[str] | None = None,
) -> tuple[Path, Path]:
    promoted_manifest = copy.deepcopy(manifest)
    target_date = str(promoted_manifest.get("query", {}).get("end_date") or "")
    unpromoted_dates: list[str] = []
    if not target_receipt_valid:
        query = promoted_manifest.get("query")
        if isinstance(query, dict):
            query["start_date"] = target_date
            query["end_date"] = target_date
        promoted_manifest["written_trade_dates"] = []
        promoted_manifest["skipped_trade_dates"] = []
        promoted_manifest["empty_trade_dates"] = (
            [target_date] if negative_reason == "target_empty" else []
        )
        totals = promoted_manifest.get("totals")
        if isinstance(totals, dict):
            totals.update(
                {
                    "rows": 0,
                    "symbols": 0,
                    "trade_dates_requested": 1,
                    "trade_dates_written": 0,
                    "trade_dates_skipped": 0,
                    "trade_dates_empty": 1 if negative_reason == "target_empty" else 0,
                    "files": 0,
                }
            )
        if promoted_manifest.get("dataset") == "dc_concept_cons":
            completeness = promoted_manifest.get("completeness")
            receipts = completeness.get("trade_dates") if isinstance(completeness, dict) else {}
            target_receipt = receipts.get(target_date) if isinstance(receipts, dict) else None
            if not isinstance(target_receipt, dict):
                target_receipt = {"trade_date": target_date}
            target_receipt = {
                **target_receipt,
                "trade_date": target_date,
                "complete": False,
                "source": "staged_negative_receipt",
            }
            promoted_manifest["complete"] = False
            promoted_manifest["completeness"] = {
                "complete": False,
                "method": (completeness.get("method") if isinstance(completeness, dict) else None),
                "complete_trade_dates": [],
                "incomplete_trade_dates": [target_date],
                "trade_dates": {target_date: target_receipt},
            }
            if isinstance(totals, dict):
                totals.update(
                    {
                        "pages": 0,
                        "distinct_themes": 0,
                        "complete_trade_dates": 0,
                        "incomplete_trade_dates": 1,
                    }
                )
    elif promoted_manifest.get("dataset") == "dc_concept_cons" and promoted_dates is not None:
        unpromoted_dates = _sanitize_dc_promotion_manifest(promoted_manifest, promoted_dates)
    promoted_manifest["output_dir"] = str(destination_dir)
    refresh_promotion = {
        "target_receipt_valid": target_receipt_valid,
        "negative_receipt": not target_receipt_valid,
        "parquet_promoted": target_receipt_valid,
    }
    if negative_reason is not None:
        refresh_promotion["negative_reason"] = negative_reason
    if promoted_dates is not None:
        refresh_promotion["promoted_dates"] = list(promoted_dates)
        refresh_promotion["unpromoted_dates"] = unpromoted_dates
    promoted_manifest["refresh_promotion"] = refresh_promotion
    destination = destination_dir / "manifest.yml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{run_id}.tmp")
    _write_manifest_temp(temporary, promoted_manifest)
    return temporary, destination


def _validate_manifest(
    manifest: dict[str, Any],
    *,
    dataset: str,
    stage_dir: Path,
    target_date: str,
    expected_dates: tuple[str, ...],
) -> tuple[list[str], list[str], list[str], list[str]]:
    manifest_dataset = str(manifest.get("dataset") or "")
    if manifest_dataset != dataset:
        raise PromotionValidationError(
            "manifest_dataset_mismatch",
            f"staged manifest dataset is {manifest_dataset!r}, expected {dataset!r}",
        )
    if manifest.get("status") != "completed":
        raise PromotionValidationError(
            "manifest_incomplete", "staged manifest status is not completed"
        )

    query = manifest.get("query")
    if not isinstance(query, dict):
        raise PromotionValidationError("manifest_invalid", "staged manifest query is missing")
    if (
        str(query.get("start_date")) != expected_dates[0]
        or str(query.get("end_date")) != target_date
    ):
        raise PromotionValidationError(
            "manifest_window_mismatch",
            "staged manifest query window does not match the effective trading window",
        )

    written_dates = _date_list(manifest.get("written_trade_dates"))
    empty_dates = _date_list(manifest.get("empty_trade_dates"))
    skipped_dates = _date_list(manifest.get("skipped_trade_dates"))
    expected = set(expected_dates)
    observed = set(written_dates) | set(empty_dates) | set(skipped_dates)
    if skipped_dates:
        raise PromotionValidationError(
            "manifest_skipped_dates", "a fresh staging mirror unexpectedly skipped dates"
        )
    if observed != expected:
        raise PromotionValidationError(
            "manifest_window_mismatch",
            f"staged manifest covered {sorted(observed)!r}, expected {sorted(expected)!r}",
        )
    if set(written_dates) & set(empty_dates):
        raise PromotionValidationError(
            "manifest_invalid", "staged manifest marks dates as both written and empty"
        )

    totals = manifest.get("totals")
    requested_count = totals.get("trade_dates_requested") if isinstance(totals, dict) else None
    if requested_count != len(expected_dates):
        raise PromotionValidationError(
            "manifest_window_mismatch",
            "staged manifest trade_dates_requested does not match the effective window",
        )

    complete_dates = list(written_dates)
    if dataset == "dc_concept_cons":
        completeness = manifest.get("completeness")
        receipts = completeness.get("trade_dates") if isinstance(completeness, dict) else None
        if not isinstance(receipts, dict):
            raise PromotionValidationError(
                "dc_completeness_missing", "dc_concept_cons completeness receipts are missing"
            )
        complete_dates = [
            trade_date
            for trade_date in written_dates
            if _dc_receipt_matches_partition(
                receipts.get(trade_date),
                _partition_path(stage_dir, trade_date),
                trade_date,
            )
        ]
    return written_dates, empty_dates, skipped_dates, complete_dates


def _replace_with_rollback(
    replacements: list[tuple[Path, Path]],
    *,
    run_id: str,
) -> None:
    backups: dict[Path, Path | None] = {}
    replaced: list[Path] = []
    try:
        for temporary, destination in replacements:
            backup: Path | None = None
            if destination.is_file():
                backup = destination.with_name(f".{destination.name}.{run_id}.backup")
                shutil.copy2(destination, backup)
            backups[destination] = backup
            os.replace(temporary, destination)
            replaced.append(destination)
    except Exception:
        for destination in reversed(replaced):
            backup = backups[destination]
            if backup is None:
                destination.unlink(missing_ok=True)
            elif backup.is_file():
                os.replace(backup, destination)
        raise
    finally:
        for backup in backups.values():
            if backup is not None:
                backup.unlink(missing_ok=True)


def _promote_negative_manifest(
    manifest: dict[str, Any],
    *,
    destination_dir: Path,
    run_id: str,
    temporary_paths: list[Path],
    receipt: dict[str, Any],
    reason: str,
) -> None:
    temporary, destination = _manifest_replacement(
        manifest,
        destination_dir=destination_dir,
        run_id=run_id,
        target_receipt_valid=False,
        negative_reason=reason,
    )
    temporary_paths.append(temporary)
    _replace_with_rollback([(temporary, destination)], run_id=run_id)
    receipt["negative_receipt_promoted"] = True
    receipt["manifest_promoted"] = True


def _promote_validated_manifest(
    manifest: dict[str, Any],
    *,
    dataset: str,
    stage_dir: Path,
    destination_dir: Path,
    target_date: str,
    expected_dates: tuple[str, ...],
    run_id: str,
    temporary_paths: list[Path],
    receipt: dict[str, Any],
) -> None:
    written, empty, skipped, complete = _validate_manifest(
        manifest,
        dataset=dataset,
        stage_dir=stage_dir,
        target_date=target_date,
        expected_dates=expected_dates,
    )
    receipt.update(
        {
            "written_dates": written,
            "empty_dates": empty,
            "skipped_dates": skipped,
            "complete_dates": complete,
            "manifest_complete": (
                len(complete) == len(expected_dates)
                if dataset == "dc_concept_cons"
                else manifest.get("complete")
            ),
            "staging_validated": True,
        }
    )
    if target_date in empty:
        _promote_negative_manifest(
            manifest,
            destination_dir=destination_dir,
            run_id=run_id,
            temporary_paths=temporary_paths,
            receipt=receipt,
            reason="target_empty",
        )
        raise PromotionValidationError(
            "target_empty", f"target date {target_date} was empty in the staged mirror"
        )
    if target_date not in written:
        raise PromotionValidationError(
            "target_receipt_missing",
            f"target date {target_date} has no written receipt in the staged manifest",
        )
    if dataset == "dc_concept_cons" and target_date not in complete:
        _promote_negative_manifest(
            manifest,
            destination_dir=destination_dir,
            run_id=run_id,
            temporary_paths=temporary_paths,
            receipt=receipt,
            reason="target_incomplete",
        )
        raise PromotionValidationError(
            "target_incomplete",
            f"target date {target_date} lacks a complete dc_concept_cons receipt",
        )

    replacements: list[tuple[Path, Path]] = []
    promotable_dates = complete if dataset == "dc_concept_cons" else written
    for trade_date in promotable_dates:
        source = _partition_path(stage_dir, trade_date)
        _require_nonempty_partition(source, trade_date=trade_date)
        destination = _partition_path(destination_dir, trade_date)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{run_id}.tmp")
        shutil.copy2(source, temporary)
        _require_nonempty_partition(temporary, trade_date=trade_date)
        temporary_paths.append(temporary)
        replacements.append((temporary, destination))

    temporary_manifest, destination_manifest = _manifest_replacement(
        manifest,
        destination_dir=destination_dir,
        run_id=run_id,
        target_receipt_valid=True,
        promoted_dates=promotable_dates,
    )
    temporary_paths.append(temporary_manifest)
    replacements.append((temporary_manifest, destination_manifest))
    _replace_with_rollback(replacements, run_id=run_id)
    receipt["target_receipt_valid"] = True
    receipt["promoted_dates"] = promotable_dates
    receipt["manifest_promoted"] = True


def promote_staged_dataset(
    *,
    dataset: str,
    stage_dir: Path,
    destination_dir: Path,
    target_date: str,
    expected_dates: tuple[str, ...],
    receipt_path: Path,
) -> dict[str, Any]:
    """Validate staged partitions and atomically promote a complete target receipt."""
    receipt: dict[str, Any] = {
        "dataset": dataset,
        "target_date": target_date,
        "expected_dates": list(expected_dates),
        "staging_validated": False,
        "target_receipt_valid": False,
        "negative_receipt_promoted": False,
        "manifest_promoted": False,
        "promoted_dates": [],
        "written_dates": [],
        "empty_dates": [],
        "skipped_dates": [],
        "complete_dates": [],
        "manifest_complete": None,
        "validation_error_code": None,
        "validation_error": None,
    }
    run_id = uuid.uuid4().hex
    temporary_paths: list[Path] = []
    try:
        if not expected_dates or expected_dates[-1] != target_date:
            raise PromotionValidationError(
                "effective_window_invalid", "effective trading window must end on target_date"
            )
        stage_dir = stage_dir.resolve()
        destination_dir = destination_dir.resolve()
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        if stage_dir.stat().st_dev != destination_dir.parent.stat().st_dev:
            raise PromotionValidationError(
                "staging_filesystem_mismatch",
                "staging and destination must be on the same filesystem",
            )

        manifest_path = stage_dir / "manifest.yml"
        manifest = _load_manifest(manifest_path)
        _promote_validated_manifest(
            manifest,
            dataset=dataset,
            stage_dir=stage_dir,
            destination_dir=destination_dir,
            target_date=target_date,
            expected_dates=expected_dates,
            run_id=run_id,
            temporary_paths=temporary_paths,
            receipt=receipt,
        )
    except PromotionValidationError as exc:
        receipt["validation_error_code"] = exc.code
        receipt["validation_error"] = str(exc)
    except Exception as exc:  # pragma: no cover - defensive filesystem boundary
        receipt["validation_error_code"] = "promotion_error"
        receipt["validation_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
        _write_json_atomic(receipt_path, receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    promote = subparsers.add_parser("promote", help="Validate and promote a staged mirror")
    promote.add_argument("--dataset", required=True)
    promote.add_argument("--stage-dir", required=True, type=Path)
    promote.add_argument("--destination-dir", required=True, type=Path)
    promote.add_argument("--target-date", required=True)
    promote.add_argument("--expected-dates", required=True)
    promote.add_argument("--receipt", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    expected_dates = tuple(part for part in args.expected_dates.split(",") if part)
    receipt = promote_staged_dataset(
        dataset=args.dataset,
        stage_dir=args.stage_dir,
        destination_dir=args.destination_dir,
        target_date=args.target_date,
        expected_dates=expected_dates,
        receipt_path=args.receipt,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["target_receipt_valid"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
