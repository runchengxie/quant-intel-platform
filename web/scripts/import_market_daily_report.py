"""Compatibility entry point for platform-owned public publication."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_publication.import_market_daily_report import _markdown as _markdown
from market_intel_publication.import_market_daily_report import _normalize as _normalize
from market_intel_publication.import_market_daily_report import import_report as import_report

_owner = importlib.import_module("market_intel_publication.import_market_daily_report")

if __name__ == "__main__":
    result = _owner.main()
    if isinstance(result, int):
        raise SystemExit(result)
else:
    sys.modules[__name__] = _owner
