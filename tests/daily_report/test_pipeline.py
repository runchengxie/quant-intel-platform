from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report.models import MarketFact
from daily_messenger.daily_report.pipeline import run_daily_report
from daily_messenger.etl.types import QuoteSnapshot

AS_OF = datetime(2026, 9, 19, 1, tzinfo=UTC)


def test_pipeline_keeps_facts_when_research_provider_fails(tmp_path):
    report = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "fail"})
    assert report.source_status["research"]["quality"] == "degraded"
    assert report.facts


def test_second_run_reuses_same_artifact_hash(tmp_path):
    first = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "fixture"})
    second = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "fixture"})
    assert first.run_id == second.run_id
    assert first.content_hash == second.content_hash


@pytest.mark.parametrize(
    ("missing", "expected_quality"),
    [({}, "ok"), ({"GC=F": "RuntimeError: provider unavailable"}, "degraded")],
)
def test_pipeline_records_cross_asset_coverage(monkeypatch, tmp_path, missing, expected_quality):
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_us_macro_facts",
        lambda _as_of: ([], {"macro": {"quality": "ok"}, "rates": {"quality": "ok"}}),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_cross_asset_facts",
        lambda _date: ([], missing),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_btc_spot_facts",
        lambda _date: ([], "all_spot_sources_unavailable"),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.index_quotes.fetch_yahoo_daily_snapshot",
        lambda _symbol, *, target_date: QuoteSnapshot(
            target_date.isoformat(), 100.0, 0.2, "yahoo:test"
        ),
    )

    report = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "live"})
    section = next(section for section in report.sections if section.key == "cross_asset")

    assert section.facts == ()
    assert report.source_status["cross_asset"]["quality"] == expected_quality
    assert report.source_status["cross_asset"]["missing_contracts"] == missing
    assert ("cross_asset" in report.missing_sources) is bool(missing)
    assert "fred" not in report.missing_sources
    assert report.quality_summary["status"] == "degraded"


def test_live_pipeline_publishes_complete_same_day_index_set(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_us_macro_facts",
        lambda _as_of: ([], {"macro": {"quality": "ok"}, "rates": {"quality": "ok"}}),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_cross_asset_facts",
        lambda _date: ([], {}),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.index_quotes.fetch_yahoo_daily_snapshot",
        lambda _symbol, *, target_date: QuoteSnapshot(
            target_date.isoformat(), 100.0, 0.2, "yahoo:test"
        ),
    )

    report = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "live"})

    index_ids = {fact.id for fact in report.facts if fact.id.startswith("index.")}
    assert index_ids == {
        "index.spx.change_percent",
        "index.dow.change_percent",
        "index.nasdaq.change_percent",
        "index.russell2000.change_percent",
    }
    assert report.source_status["quotes"]["quality"] == "ok"
    assert "quotes" not in report.missing_sources
    assert index_ids <= set(report.sections[0].facts)


def test_live_pipeline_keeps_btc_spot_separate_from_futures(monkeypatch, tmp_path):
    spot = MarketFact(
        id="cross_asset.bitcoin_spot.close",
        metric="crypto_spot_close",
        instrument="BTC/USD cryptocurrency EOD (FMP BTCUSD)",
        value=84093.13,
        previous=None,
        change=None,
        unit="USD/bitcoin",
        source="Financial Modeling Prep",
        source_url="https://site.financialmodelingprep.com/developer/docs/stable/cryptocurrency-historical-price-eod-full",
        source_time=AS_OF,
        retrieved_at=AS_OF,
        quality="ok",
        observation_date="2026-09-18",
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_us_macro_facts",
        lambda _as_of: ([], {"macro": {"quality": "ok"}, "rates": {"quality": "ok"}}),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_cross_asset_facts",
        lambda _date: ([], {}),
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.pipeline.fetch_btc_spot_facts",
        lambda _date: ([spot], "ok"),
        raising=False,
    )
    monkeypatch.setattr(
        "daily_messenger.daily_report.index_quotes.fetch_yahoo_daily_snapshot",
        lambda _symbol, *, target_date: QuoteSnapshot(
            target_date.isoformat(), 100.0, 0.2, "yahoo:test"
        ),
    )

    report = run_daily_report(AS_OF, tmp_path, provider_config={"mode": "live"})

    assert spot.id in {fact.id for fact in report.facts}
    assert (
        spot.id
        in next(section for section in report.sections if section.key == "cross_asset").facts
    )
    assert report.source_status["btc_spot"]["quality"] == "ok"
