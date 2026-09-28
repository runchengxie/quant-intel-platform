"""Compatibility entry point for platform-owned market commentary."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_commentary.insight_provider import (
    ANALYSIS_SCHEMA as ANALYSIS_SCHEMA,
)
from market_intel_commentary.insight_provider import (
    generate as generate,
)

_owner = importlib.import_module("market_intel_commentary.insight_provider")

if __name__ != "__main__":
    sys.modules[__name__] = _owner
