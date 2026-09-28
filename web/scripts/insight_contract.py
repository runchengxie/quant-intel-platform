"""Compatibility entry point for platform-owned market commentary."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_commentary.insight_contract import (
    build_context as build_context,
)
from market_intel_commentary.insight_contract import (
    evaluate_watchpoints as evaluate_watchpoints,
)
from market_intel_commentary.insight_contract import (
    source_hash as source_hash,
)
from market_intel_commentary.insight_contract import (
    validate_analysis as validate_analysis,
)

_owner = importlib.import_module("market_intel_commentary.insight_contract")

if __name__ != "__main__":
    sys.modules[__name__] = _owner
