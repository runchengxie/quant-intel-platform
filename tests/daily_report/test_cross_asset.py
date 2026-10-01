from datetime import date

import pytest

from daily_messenger.daily_report.cross_asset import dated_contract_symbol, fetch_cross_asset_facts
from daily_messenger.etl.types import QuoteSnapshot


def test_cross_asset_facts_include_price_and_percent_change_for_each_contract(monkeypatch):
    snapshots = {
        "BZX26.NYM": QuoteSnapshot("2026-09-24", 71.25, 1.2, "yahoo:BZX26.NYM"),
        "GCZ26.CMX": QuoteSnapshot("2026-09-24", 3980.5, -0.3, "yahoo:GCZ26.CMX"),
        "SIZ26.CMX": QuoteSnapshot("2026-09-24", 47.12, 0.8, "yahoo:SIZ26.CMX"),
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
    assert by_id["cross_asset.silver.close"].source_url.endswith("SIZ26.CMX/history/")


def test_dated_contracts_use_one_delivery_month_on_both_sides_of_roll():
    assert dated_contract_symbol("BZ=F", date(2026, 9, 25)) == "BZX26.NYM"
    assert dated_contract_symbol("BZ=F", date(2026, 10, 1)) == "BZZ26.NYM"
    assert dated_contract_symbol("BZ=F", date(2026, 12, 1)) == "BZG27.NYM"
    assert dated_contract_symbol("GC=F", date(2026, 9, 25)) == "GCZ26.CMX"
    assert dated_contract_symbol("SI=F", date(2026, 9, 25)) == "SIZ26.CMX"


def test_brent_report_does_not_use_rolled_continuous_return(monkeypatch):
    from daily_messenger.daily_report import cross_asset

    requested = []

    def fetch(symbol, *, target_date, completed_after=None):
        requested.append(symbol)
        if symbol == "BZX26.NYM":
            return QuoteSnapshot("2026-09-25", 104.32, -2.1388, f"yahoo:{symbol}")
        if symbol == "BZ=F":
            return QuoteSnapshot("2026-09-25", 97.44, -8.5929, f"yahoo:{symbol}")
        return QuoteSnapshot("2026-09-25", 100.0, 1.0, f"yahoo:{symbol}")

    monkeypatch.setattr(cross_asset, "fetch_yahoo_daily_snapshot", fetch)
    facts, missing = cross_asset.fetch_cross_asset_facts(date(2026, 9, 25))
    brent = next(fact for fact in facts if fact.id == "cross_asset.brent.change_percent")
    assert not missing
    assert brent.value == -2.1388
    assert "BZX26.NYM" in brent.source_url
    assert "BZ=F" not in requested


def test_cross_asset_wrong_date_and_one_failed_contract_are_missing_without_dropping_others(
    monkeypatch,
):
    def fetch(symbol, *, target_date, completed_after=None):
        assert target_date == date(2026, 9, 24)
        if symbol == "GCZ26.CMX":
            raise RuntimeError("provider unavailable")
        day = "2026-09-23" if symbol == "BTC=F" else "2026-09-24"
        return QuoteSnapshot(day, 100.0, 1.0, f"yahoo:{symbol}")

    monkeypatch.setattr(
        "daily_messenger.daily_report.cross_asset.fetch_yahoo_daily_snapshot", fetch
    )
    facts, missing = fetch_cross_asset_facts(date(2026, 9, 24))

    assert len(facts) == 4
    assert missing == {
        "GC=F": "provider_unavailable",
        "BTC=F": "observation_date_mismatch",
    }
    assert not any(fact.id.startswith("cross_asset.gold.") for fact in facts)
    assert not any(fact.id.startswith("cross_asset.bitcoin.") for fact in facts)


def test_missing_dated_contract_does_not_substitute_continuous_fmp(monkeypatch):
    from daily_messenger.daily_report import cross_asset

    def yahoo(symbol, *, target_date, completed_after=None):
        if symbol == "BZX26.NYM":
            raise RuntimeError("Yahoo unavailable")
        return QuoteSnapshot(target_date.isoformat(), 100.0, 1.0, f"yahoo:{symbol}")

    monkeypatch.setattr(cross_asset, "fetch_yahoo_daily_snapshot", yahoo)
    monkeypatch.setattr(
        cross_asset,
        "fetch_fmp_daily_snapshot",
        lambda *args, **kwargs: pytest.fail("continuous fallback must not be used"),
        raising=False,
    )

    facts, missing = cross_asset.fetch_cross_asset_facts(date(2026, 9, 24))
    by_id = {fact.id: fact for fact in facts}

    assert missing == {"BZ=F": "provider_unavailable"}
    assert "cross_asset.brent.close" not in by_id
    assert by_id["cross_asset.gold.close"].source == "Yahoo Finance"
    assert by_id["cross_asset.bitcoin.close"].source == "Yahoo Finance"


def test_fmp_eod_requires_target_and_previous_daily_closes(monkeypatch):
    from daily_messenger.daily_report.fmp_prices import fetch_fmp_daily_snapshot

    class Response:
        status_code = 200

        def json(self):
            return [
                {"symbol": "BZUSD", "date": "2026-09-24", "close": 102.0},
                {"symbol": "BZUSD", "date": "2026-09-23", "close": 100.0},
            ]

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response())
    snapshot = fetch_fmp_daily_snapshot("BZUSD", target_date=date(2026, 9, 24), api_key="key")
    assert snapshot.day == "2026-09-24"
    assert snapshot.close == 102.0
    assert snapshot.change_pct == pytest.approx(2.0)


def test_fmp_eod_rejects_missing_target_day(monkeypatch):
    from daily_messenger.daily_report.fmp_prices import fetch_fmp_daily_snapshot

    class Response:
        status_code = 200

        def json(self):
            return [{"symbol": "BZUSD", "date": "2026-09-23", "close": 100.0}]

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="target date"):
        fetch_fmp_daily_snapshot("BZUSD", target_date=date(2026, 9, 24), api_key="key")


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
