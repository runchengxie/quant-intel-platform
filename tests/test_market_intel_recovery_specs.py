from __future__ import annotations

from ops_common.market_intel_recovery import MARKET_INTEL_SPECS
from ops_common.scheduled_recovery import DEFAULT_SPECS


def test_market_intel_recovery_excludes_research_factor_pipeline() -> None:
    keys = {spec.key for spec in MARKET_INTEL_SPECS}
    assert "factor_pipeline" not in keys
    assert "factor_pipeline" not in {spec.key for spec in DEFAULT_SPECS}
    assert {"daily_market", "current_contract", "morning_model", "morning_report"} <= keys
