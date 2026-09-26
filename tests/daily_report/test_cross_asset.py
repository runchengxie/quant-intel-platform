from datetime import date

import pytest

from daily_messenger.daily_report.cross_asset import fetch_cross_asset_facts
from daily_messenger.etl.types import QuoteSnapshot


def test_cross_asset_facts_include_price_and_percent_change_for_each_contract(monkeypatch):
    snapshots = {
        "BZ=F": QuoteSnapshot("2026-09-24", 71.25, 1.2, "yahoo:BZ=F"),
        "GC=F": QuoteSnapshot("2026-09-24", 3980.5, -0.3, "yahoo:GC=F"),
        "SI=F": QuoteSnapshot("2026-09-24", 47.12, 0.8, "yahoo:SI=F"),
        "BTC=F": QuoteSnapshot("2026-09-24", 108500.0, 2.4, "yahoo:BTC=F"),
    }
    monkeypatch.setattr(
        "daily_messenger.daily_report.cross_asset.fetch_yahoo_daily_snapshot",
        lambda symbol, *, target_date, completed_after=None: (
            snapshots[symbol] if target_date == date(2026, 9, 24) else None
        ),
    )

    facts, missing = fetch_cross_asset_facts(date(2026, 9, 24))
    by_id = {fact.id: fact for fact in facts}

    assert not missing
    assert len(facts) == 8
    assert by_id["cross_asset.brent.close"].value == 71.25
    assert by_id["cross_asset.brent.close"].unit == "USD/barrel"
    assert by_id["cross_asset.brent.change_percent"].value == 1.2
    assert by_id["cross_asset.bitcoin.close"].unit == "USD/bitcoin"
    assert by_id["cross_asset.gold.close"].observation_date == "2026-09-24"
    assert by_id["cross_asset.silver.close"].source_url.endswith("SI%3DF/history/")


def test_cross_asset_wrong_date_and_one_failed_contract_are_missing_without_dropping_others(
    monkeypatch,
):
    def fetch(symbol, *, target_date, completed_after=None):
        assert target_date == date(2026, 9, 24)
        if symbol == "GC=F":
            raise RuntimeError("provider unavailable")
        day = "2026-09-23" if symbol == "BTC=F" else "2026-09-24"
        return QuoteSnapshot(day, 100.0, 1.0, f"yahoo:{symbol}")

    monkeypatch.setattr(
        "daily_messenger.daily_report.cross_asset.fetch_yahoo_daily_snapshot", fetch
    )
    facts, missing = fetch_cross_asset_facts(date(2026, 9, 24))

    assert len(facts) == 4
    assert missing == {
        "GC=F": "RuntimeError: provider unavailable",
        "BTC=F": "observation_date_mismatch",
    }
    assert not any(fact.id.startswith("cross_asset.gold.") for fact in facts)
    assert not any(fact.id.startswith("cross_asset.bitcoin.") for fact in facts)


def test_yahoo_daily_snapshot_uses_exchange_timezone_for_observation_date(monkeypatch):
    from daily_messenger.etl.fetchers import quotes

    monkeypatch.setattr(
        "daily_messenger.etl.fetchers.quotes._fetch_yahoo_chart",
        lambda _symbol: {
            "meta": {"exchangeTimezoneName": "America/New_York"},
            "timestamp": [1790200800, 1790287200],
            "indicators": {"quote": [{"close": [100.0, 102.0]}]},
        },
    )

    snapshot = quotes.fetch_yahoo_daily_snapshot("BZ=F")

    assert snapshot.day == "2026-09-24"
    assert snapshot.close == 102.0
    assert snapshot.change_pct == 2.0


def test_yahoo_daily_snapshot_rejects_missing_exchange_timezone(monkeypatch):
    from daily_messenger.etl.fetchers import quotes

    monkeypatch.setattr(
        "daily_messenger.etl.fetchers.quotes._fetch_yahoo_chart",
        lambda _symbol: {
            "meta": {},
            "timestamp": [1, 2],
            "indicators": {"quote": [{"close": [100.0, 102.0]}]},
        },
    )

    with pytest.raises(RuntimeError, match="timezone"):
        quotes.fetch_yahoo_daily_snapshot("BZ=F")


def test_yahoo_daily_snapshot_rejects_active_daily_bar(monkeypatch):
    from datetime import UTC, datetime

    from daily_messenger.etl.fetchers import quotes

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 9, 25, 2, tzinfo=UTC)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(quotes, "datetime", FixedDateTime)
    monkeypatch.setattr(
        "daily_messenger.etl.fetchers.quotes._fetch_yahoo_chart",
        lambda _symbol: {
            "meta": {
                "exchangeTimezoneName": "America/New_York",
                "currentTradingPeriod": {"regular": {"start": 1790265600, "end": 1790301600}},
            },
            "timestamp": [1790200800, 1790287200],
            "indicators": {"quote": [{"close": [100.0, 102.0]}]},
        },
    )

    with pytest.raises(RuntimeError, match="未完成"):
        quotes.fetch_yahoo_daily_snapshot("BZ=F")


def test_yahoo_future_accepts_dated_bar_after_independent_close_cutoff(monkeypatch):
    from datetime import UTC, datetime, time

    from daily_messenger.etl.fetchers import quotes

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 9, 25, 22, 45, tzinfo=UTC)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(quotes, "datetime", FixedDateTime)
    monkeypatch.setattr(
        quotes,
        "_fetch_yahoo_chart",
        lambda _symbol: {
            "meta": {
                "exchangeTimezoneName": "America/New_York",
                "currentTradingPeriod": {
                    "regular": {"end": int(datetime(2026, 9, 26, 3, 59, tzinfo=UTC).timestamp())}
                },
            },
            "timestamp": [1790287200, 1790373600],
            "indicators": {"quote": [{"close": [100.0, 102.0]}]},
        },
    )

    snapshot = quotes.fetch_yahoo_daily_snapshot(
        "BZ=F", target_date=date(2026, 9, 25), completed_after=time(18)
    )

    assert snapshot.day == "2026-09-25"
    assert snapshot.close == 102.0
    assert snapshot.change_pct == 2.0


def test_yahoo_daily_snapshot_selects_completed_requested_day_behind_active_bar(monkeypatch):
    from datetime import UTC, date, datetime

    from daily_messenger.etl.fetchers import quotes

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 9, 25, 15, tzinfo=UTC)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(quotes, "datetime", FixedDateTime)
    monkeypatch.setattr(
        quotes,
        "_fetch_yahoo_chart",
        lambda _symbol: {
            "meta": {"exchangeTimezoneName": "America/New_York"},
            "timestamp": [1790200800, 1790287200, 1790373600],
            "indicators": {"quote": [{"close": [100.0, 102.0, 110.0]}]},
        },
    )

    snapshot = quotes.fetch_yahoo_daily_snapshot("BZ=F", target_date=date(2026, 9, 24))

    assert snapshot.day == "2026-09-24"
    assert snapshot.close == 102.0
    assert snapshot.change_pct == 2.0


def test_yahoo_daily_snapshot_rejects_absent_requested_day(monkeypatch):
    from datetime import date

    from daily_messenger.etl.fetchers import quotes

    monkeypatch.setattr(
        quotes,
        "_fetch_yahoo_chart",
        lambda _symbol: {
            "meta": {"exchangeTimezoneName": "America/New_York"},
            "timestamp": [1790200800, 1790373600],
            "indicators": {"quote": [{"close": [100.0, 110.0]}]},
        },
    )

    with pytest.raises(RuntimeError, match="指定交易日"):
        quotes.fetch_yahoo_daily_snapshot("BZ=F", target_date=date(2026, 9, 24))
