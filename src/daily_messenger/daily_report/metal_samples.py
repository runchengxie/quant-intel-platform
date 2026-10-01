"""Immutable private reference samples; not public report facts."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from daily_messenger.daily_report.gold_reference import fetch_reference_quote

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _validate_output(output: Path) -> None:
    if (
        output == PROJECT_ROOT
        or PROJECT_ROOT in output.parents
        or any(
            (parent / ".git").is_file() or (parent / ".git" / "HEAD").is_file()
            for parent in (output, *output.parents)
        )
    ):
        raise ValueError("metal samples must be outside the repository")
    if output.exists():
        stat = output.stat()
        if not output.is_dir() or stat.st_uid != os.getuid() or stat.st_mode & 0o022:
            raise ValueError("metal samples require a private, owner-controlled directory")


def sample_metals(output_dir: Path) -> Path:
    """Save a complete pair without exposing provider errors or credentials."""
    output = output_dir.resolve()
    _validate_output(output)
    quotes = [fetch_reference_quote(symbol) for symbol in ("XAU", "XAG")]
    payload = {
        "schema_version": "1.0",
        "publication": "private",
        "provider": "gold-api.com",
        "currency": "USD",
        "instrument": "unverified",
        "quotation_unit": "unverified",
        "quotes": [asdict(quote) for quote in quotes],
    }
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    _validate_output(output)
    target = output / f"metal-reference-{uuid4().hex}.json"
    temporary = output / f".{target.name}.tmp"
    created = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, default=lambda value: value.isoformat(), indent=2)
            handle.write("\n")
        os.link(temporary, target)
    finally:
        if created:
            temporary.unlink(missing_ok=True)
    return target
