from datetime import date, time

import pytest

from daily_messenger.etl.types import QuoteSnapshot


def test_fmp_btc_spot_is_separate_from_cme_futures(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    monkeypatch.setattr(btc_spot, "resolve_api_key", lambda _key: "secret")
    monkeypatch.setattr(
        btc_spot,
        "fetch_fmp_daily_snapshot",
        lambda symbol, *, target_date, api_key, completed_after: (
            QuoteSnapshot(target_date.isoformat(), 84093.13, -0.3464, f"fmp:{symbol}")
            if completed_after == time(18, 15)
            else None
        ),
    )
    monkeypatch.setattr(
        btc_spot,
        "fetch_kraken_spot_snapshot",
        lambda _date: (_ for _ in ()).throw(RuntimeError("not needed")),
    )

    facts, status = btc_spot.fetch_btc_spot_facts(date(2026, 9, 25))

    assert status == "ok"
    assert [fact.id for fact in facts] == [
        "cross_asset.bitcoin_spot.close",
        "cross_asset.bitcoin_spot.change_percent",
    ]
    assert facts[0].metric == "crypto_spot_close"
    assert facts[0].source == "Financial Modeling Prep"
    assert facts[0].value == 84093.13
    assert facts[0].observation_date == "2026-09-25"
    assert facts[1].value == pytest.approx(-0.3464)


def test_kraken_fallback_uses_two_completed_same_cutoff_bars(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    class Response:
        status_code = 200

        def json(self):
            return {
                "error": [],
                "result": {
                    "XXBTZUSD": [
                        [1790190000, "100", "103", "99", "100", "100", "1", 10],
                        [1790276400, "100", "105", "99", "104", "102", "1", 10],
                        [1790280000, "104", "105", "103", "105", "105", "1", 10],
                    ],
                    "last": 1790280000,
                },
            }

    monkeypatch.setattr(btc_spot.requests, "get", lambda *args, **kwargs: Response())
    snapshot = btc_spot.fetch_kraken_spot_snapshot(date(2026, 9, 24))

    assert snapshot.day == "2026-09-24"
    assert snapshot.close == 104
    assert snapshot.change_pct == pytest.approx(4.0)


def test_kraken_fallback_rejects_missing_prior_cutoff(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    class Response:
        status_code = 200

        def json(self):
            return {
                "error": [],
                "result": {
                    "XXBTZUSD": [
                        [1790276400, "100", "105", "99", "104", "102", "1", 10],
                        [1790280000, "104", "105", "103", "105", "105", "1", 10],
                    ],
                    "last": 1790280000,
                },
            }

    monkeypatch.setattr(btc_spot.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="previous cutoff"):
        btc_spot.fetch_kraken_spot_snapshot(date(2026, 9, 24))


def test_kraken_private_fallback_never_becomes_public_fact(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    monkeypatch.setattr(btc_spot, "resolve_api_key", lambda _key: "secret")

    def failed_fmp(*args, **kwargs):
        raise RuntimeError("FMP unavailable")

    monkeypatch.setattr(btc_spot, "fetch_fmp_daily_snapshot", failed_fmp)
    monkeypatch.setattr(
        btc_spot,
        "fetch_kraken_spot_snapshot",
        lambda _date: QuoteSnapshot("2026-09-24", 104.0, 4.0, "kraken:XBTUSD:16ET"),
    )

    facts, status = btc_spot.fetch_btc_spot_facts(date(2026, 9, 24))

    assert facts == []
    assert status == "kraken_private_fallback_only"
