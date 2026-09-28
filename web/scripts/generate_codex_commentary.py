"""Compatibility entry point for platform-owned market commentary."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_commentary.generate_codex_commentary import (
    run as run,
)

_owner = importlib.import_module("market_intel_commentary.generate_codex_commentary")

if __name__ == "__main__":
    raise SystemExit(_owner.main())
else:
    sys.modules[__name__] = _owner
