"""Compatibility adapter for the Platform-owned chart review contract."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_publication.chart_review import *  # noqa: F403
from market_intel_publication.chart_review import main

_owner = importlib.import_module("market_intel_publication.chart_review")
if __name__ == "__main__":
    main()
else:
    sys.modules[__name__] = _owner
