"""Compatibility adapter for the Platform-owned public chart contract."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_publication.chart_contract import *  # noqa: F403

_owner = importlib.import_module("market_intel_publication.chart_contract")
if __name__ != "__main__":
    sys.modules[__name__] = _owner
