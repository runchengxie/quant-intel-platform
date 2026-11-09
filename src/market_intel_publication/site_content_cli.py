"""Installed public content pack/verify commands; receipts are external evidence."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from market_intel_publication.site_content_codec import (
    new_output,
    pack_site_content,
    receipt_bytes,
    verify_site_content,
)


def _run(args: argparse.Namespace, *, packing: bool) -> None:
    source = args.root if packing else args.bundle
    output = new_output(args.output, (source, args.receipt))
    receipt = new_output(args.receipt, (source, output))
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix=".site-content-cli-", dir=output.parent) as work,
        tempfile.TemporaryDirectory(prefix=".site-receipt-", dir=receipt.parent) as receipts,
    ):
        staged = Path(work) / "output"
        if packing:
            result = pack_site_content(
                source,
                staged,
                created_at_utc=args.created_at,
                producer_revision=args.producer_revision,
            )
        else:
            result = verify_site_content(
                source,
                args.sha256,
                staged,
                expected_producer_revision=args.expected_producer_revision,
            )
        staged_receipt = Path(receipts) / "receipt.json"
        staged_receipt.write_bytes(receipt_bytes(result))
        new_output(output, (source, receipt))
        receipt.hardlink_to(staged_receipt)
        try:
            if packing:
                output.hardlink_to(staged)
            else:
                staged.rename(output)
        except OSError:
            receipt.unlink()
            raise
    print(f"{result.bundle_id} {result.archive_sha256}")


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output", type=Path, required=True, help="New external destination; never replaced"
    )
    parser.add_argument(
        "--receipt", type=Path, required=True, help="New external JSON receipt path"
    )


def pack_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Pack indexed public reports with measured installed VCS provenance."
    )
    parser.add_argument(
        "--root", type=Path, required=True, help="Input root containing artifacts/public"
    )
    parser.add_argument(
        "--created-at", required=True, help="Fixed UTC timestamp reused for retries"
    )
    parser.add_argument(
        "--producer-revision", required=True, help="Installed immutable 40-character Git revision"
    )
    _common(parser)
    try:
        _run(parser.parse_args(argv), packing=True)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


def verify_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Verify exact public bundle bytes and materialize a new artifacts/public root."
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="Expected exact archive byte digest")
    parser.add_argument(
        "--expected-producer-revision",
        required=True,
        help="Expected and installed immutable Git revision",
    )
    _common(parser)
    try:
        _run(parser.parse_args(argv), packing=False)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
