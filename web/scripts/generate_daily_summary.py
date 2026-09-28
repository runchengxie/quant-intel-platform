"""Compatibility entry point for platform-owned market commentary."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_intel_commentary.generate_daily_summary import (
    CHINA_TZ as CHINA_TZ,
)
from market_intel_commentary.generate_daily_summary import (
    current_summaries as current_summaries,
)
from market_intel_commentary.generate_daily_summary import (
    generate_summary as generate_summary,
)
from market_intel_commentary.generate_daily_summary import (
    report_generated_at as report_generated_at,
)
from market_intel_commentary.generate_daily_summary import (
    run as run,
)
from market_intel_commentary.generate_daily_summary import (
    select_source_pair as select_source_pair,
)
from market_intel_commentary.generate_daily_summary import (
    summary_source_hash as summary_source_hash,
)
from market_intel_commentary.generate_daily_summary import (
    validate_summary as validate_summary,
)

_owner = importlib.import_module("market_intel_commentary.generate_daily_summary")

if __name__ == "__main__":
    raise SystemExit(_owner.main())
else:
    sys.modules[__name__] = _owner
