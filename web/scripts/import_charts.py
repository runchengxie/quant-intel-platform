"""Compatibility adapter for the Platform-owned reviewed chart importer."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_publication.import_charts import *  # noqa: F403
from market_intel_publication.import_charts import main

_owner = importlib.import_module("market_intel_publication.import_charts")
if __name__ == "__main__":
    main()
else:
    sys.modules[__name__] = _owner
