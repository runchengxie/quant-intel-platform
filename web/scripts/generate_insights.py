"""Compatibility entry point for platform-owned market commentary."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_commentary.generate_insights import (
    DEFAULT_MODELS as DEFAULT_MODELS,
)
from market_intel_commentary.generate_insights import (
    SCHEMA as SCHEMA,
)
from market_intel_commentary.generate_insights import (
    _latest_insights as _latest_insights,
)
from market_intel_commentary.generate_insights import (
    _load_history as _load_history,
)
from market_intel_commentary.generate_insights import (
    _valid_history as _valid_history,
)
from market_intel_commentary.generate_insights import (
    archive_once as archive_once,
)
from market_intel_commentary.generate_insights import (
    run as run,
)
from market_intel_commentary.generate_insights import (
    write_json as write_json,
)

_owner = importlib.import_module("market_intel_commentary.generate_insights")

if __name__ == "__main__":
    _owner.main()
else:
    sys.modules[__name__] = _owner
