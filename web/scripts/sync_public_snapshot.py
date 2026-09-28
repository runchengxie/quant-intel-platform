"""Compatibility entry point for platform-owned public publication."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_publication.sync_public_snapshot import _safe_report_path as _safe_report_path
from market_intel_publication.sync_public_snapshot import sync_snapshot as sync_snapshot

_owner = importlib.import_module("market_intel_publication.sync_public_snapshot")

if __name__ == "__main__":
    result = _owner.main()
    if isinstance(result, int):
        raise SystemExit(result)
else:
    sys.modules[__name__] = _owner
