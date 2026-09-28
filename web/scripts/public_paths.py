"""Compatibility entry point for platform-owned public publication."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_publication.public_paths import public_snapshot_root as public_snapshot_root
from market_intel_publication.public_paths import safe_public_report_path as safe_public_report_path

_owner = importlib.import_module("market_intel_publication.public_paths")

if __name__ != "__main__":
    sys.modules[__name__] = _owner
