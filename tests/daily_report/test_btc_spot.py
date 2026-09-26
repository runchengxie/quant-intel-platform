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


def test_kraken_rejects_cutoff_bar_when_it_is_last_uncommitted_bar(monkeypatch):
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
                    ],
                    "last": 1790276400,
                },
            }

    monkeypatch.setattr(btc_spot.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="target cutoff"):
        btc_spot.fetch_kraken_spot_snapshot(date(2026, 9, 24))


def test_kraken_fallback_becomes_public_spot_fact(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    monkeypatch.setattr(btc_spot, "resolve_api_key", lambda _key: "secret")

    def failed_fmp(*args, **kwargs):
        raise RuntimeError("FMP unavailable")

    monkeypatch.setattr(btc_spot, "fetch_fmp_daily_snapshot", failed_fmp)
    monkeypatch.setattr(
        btc_spot,
        "fetch_coingecko_spot_snapshot",
        lambda _date, _key: (_ for _ in ()).throw(RuntimeError("CoinGecko unavailable")),
        raising=False,
    )
    monkeypatch.setattr(
        btc_spot,
        "fetch_kraken_spot_snapshot",
        lambda _date: QuoteSnapshot("2026-09-24", 104.0, 4.0, "kraken:XBTUSD:16ET"),
    )

    facts, status = btc_spot.fetch_btc_spot_facts(date(2026, 9, 24))

    assert status == "kraken_fallback"
    assert facts[0].source == "Kraken"
    assert facts[0].value == 104.0
    assert facts[1].value == 4.0


def test_coingecko_fallback_uses_completed_16et_points(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    class Response:
        status_code = 200

        def json(self):
            return {
                "prices": [
                    [1790280000000, 100.0],
                    [1790366400000, 104.0],
                    [1790370000000, 106.0],
                ],
                "market_caps": [],
                "total_volumes": [],
            }

    monkeypatch.setattr(btc_spot.requests, "get", lambda *args, **kwargs: Response())
    snapshot = btc_spot.fetch_coingecko_spot_snapshot(date(2026, 9, 25), "secret")

    assert snapshot.day == "2026-09-25"
    assert snapshot.close == 104.0
    assert snapshot.change_pct == pytest.approx(4.0)


def test_coingecko_fallback_rejects_missing_prior_cutoff(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    class Response:
        status_code = 200

        def json(self):
            return {"prices": [[1790366400000, 104.0]], "market_caps": [], "total_volumes": []}

    monkeypatch.setattr(btc_spot.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="previous cutoff"):
        btc_spot.fetch_coingecko_spot_snapshot(date(2026, 9, 25), "secret")


def test_coingecko_rejects_malformed_duplicate_cutoff(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    class Response:
        status_code = 200

        def json(self):
            return {
                "prices": [
                    [1790280000000, 100.0],
                    [1790366400000, 104.0],
                    [1790366400000],
                ]
            }

    monkeypatch.setattr(btc_spot.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="invalid"):
        btc_spot.fetch_coingecko_spot_snapshot(date(2026, 9, 25), "secret")


def test_kraken_parser_rejects_malformed_duplicate_cutoff():
    from daily_messenger.daily_report.btc_spot import _parse_kraken_closes

    cutoff = 1790276400
    with pytest.raises(RuntimeError, match="invalid"):
        _parse_kraken_closes([[cutoff, "1", "2", "1", "104"], [cutoff]], {cutoff})


def test_fmp_failure_uses_coingecko_before_kraken(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    monkeypatch.setattr(btc_spot, "resolve_api_key", lambda _key: "secret")
    monkeypatch.setattr(
        btc_spot,
        "fetch_fmp_daily_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("FMP unavailable")),
    )
    monkeypatch.setattr(
        btc_spot,
        "fetch_coingecko_spot_snapshot",
        lambda _date, _key: QuoteSnapshot("2026-09-25", 84012.8, -0.43, "coingecko:bitcoin:16ET"),
        raising=False,
    )
    monkeypatch.setattr(
        btc_spot,
        "fetch_kraken_spot_snapshot",
        lambda _date: (_ for _ in ()).throw(AssertionError("Kraken should not be used")),
    )

    facts, status = btc_spot.fetch_btc_spot_facts(date(2026, 9, 25))

    assert status == "coingecko_fallback"
    assert facts[0].source == "Data provided by CoinGecko"
    assert facts[0].value == 84012.8
    assert facts[0].instrument == "BTC/USD spot at 16:00 ET (CoinGecko bitcoin/USD)"


def test_missing_fmp_key_still_uses_coingecko(monkeypatch):
    from daily_messenger.daily_report import btc_spot

    monkeypatch.setattr(
        btc_spot,
        "resolve_api_key",
        lambda name: None if name == "financial_modeling_prep" else "secret",
    )
    monkeypatch.setattr(
        btc_spot,
        "fetch_coingecko_spot_snapshot",
        lambda _date, _key: QuoteSnapshot("2026-09-25", 104.0, 4.0, "coingecko:bitcoin:16ET"),
        raising=False,
    )

    facts, status = btc_spot.fetch_btc_spot_facts(date(2026, 9, 25))

    assert status == "coingecko_fallback"
    assert facts[0].value == 104.0
