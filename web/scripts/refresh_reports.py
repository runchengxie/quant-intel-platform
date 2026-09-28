"""Compatibility entry point for the platform-owned public report refresh."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
_owner = importlib.import_module("a_share_daily.public_report_refresh")

main = _owner.main
public_markdown = _owner.public_markdown


def refresh_reports(
    owner_cli: Path,
    data_root: Path,
    snapshot_root: Path,
    output_dir: Path,
    date: str,
    kind: str = "evening",
    *,
    generation_mode: str = "backfill",
    timeout_seconds: float = 180,
) -> Path:
    return _owner.refresh_reports(
        _owner.RefreshRequest(
            owner_cli=owner_cli,
            data_root=data_root,
            snapshot_root=snapshot_root,
            output_dir=output_dir,
            date=date,
            kind=kind,
            generation_mode=generation_mode,
            timeout_seconds=timeout_seconds,
        )
    )


if __name__ == "__main__":
    main()
