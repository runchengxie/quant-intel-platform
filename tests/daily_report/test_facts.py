from datetime import UTC, datetime

from daily_messenger.daily_report.facts import (
    build_market_facts,
    classify_curve_move,
    merge_fact_batches,
)

AS_OF = datetime(2026, 9, 19, 1, tzinfo=UTC)


def _fact(facts, fact_id):
    return next(item for item in facts if item.id == fact_id)


def test_build_market_facts_includes_curve_and_cross_market_metrics():
    payloads = {
        "treasury": {"2Y": {"change_bp": 8.0}, "5Y": {"change_bp": 6.0}, "10Y": {"change_bp": 4.0}},
        "quotes": {"SPX": {"value": 0.16, "previous": 0.0}, "WTI": {"value": -1.6, "previous": 0.0}},
    }
    facts = build_market_facts(payloads, as_of=AS_OF)
    assert _fact(facts, "treasury.2y.change_bp").value == 8.0
    assert _fact(facts, "treasury.10y.change_bp").value == 4.0
    assert _fact(facts, "cross_market.wti.change_percent").value == -1.6
    assert classify_curve_move(facts) == "bear_flattening"


def test_failed_source_is_marked_degraded_without_dropping_other_facts():
    payloads = {
        "treasury": RuntimeError("quota"),
        "quotes": {"SPX": {"value": 0.16, "previous": 0.0}},
    }
    facts = build_market_facts(payloads, as_of=AS_OF)
    assert not any(item.id == "treasury.10y.change_bp" for item in facts)
    assert _fact(facts, "index.spx.change_percent").quality == "ok"
    assert merge_fact_batches([facts]) == facts
