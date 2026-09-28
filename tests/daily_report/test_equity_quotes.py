from datetime import date

from daily_messenger.etl.types import QuoteSnapshot


def test_equity_quotes_include_core_and_reviewed_movers_with_matching_pairs(monkeypatch):
    from daily_messenger.daily_report import equity_quotes

    monkeypatch.setattr(
        equity_quotes,
        "fetch_yahoo_daily_snapshot",
        lambda symbol, *, target_date: QuoteSnapshot(
            target_date.isoformat(), 100.0, 1.25, f"yahoo:{symbol}"
        ),
    )
    facts, missing = equity_quotes.fetch_equity_facts(date(2026, 9, 25), ("AKAM", "MSFT"))
    assert missing == ()
    assert len(facts) == 2 * (len(equity_quotes.CORE_SYMBOLS) + 1)
    assert {fact.id for fact in facts if fact.id.startswith("equity.akam.")} == {
        "equity.akam.close",
        "equity.akam.change_percent",
    }
    assert all(fact.observation_date == "2026-09-25" for fact in facts)
    assert all(fact.source == "Yahoo Finance" for fact in facts)


def test_equity_quotes_use_alpaca_sip_only_when_yahoo_unavailable(monkeypatch):
    from daily_messenger.daily_report import equity_quotes

    def yahoo(symbol, *, target_date):
        if symbol == "MSFT":
            raise RuntimeError("Yahoo unavailable")
        return QuoteSnapshot(target_date.isoformat(), 100.0, 1.25, f"yahoo:{symbol}")

    monkeypatch.setattr(equity_quotes, "fetch_yahoo_daily_snapshot", yahoo)
    monkeypatch.setattr(equity_quotes, "resolve_api_key", lambda key: "test-key")
    monkeypatch.setattr(
        equity_quotes,
        "_fetch_alpaca_sip_snapshot",
        lambda symbol, report_date, key, secret: QuoteSnapshot(
            report_date.isoformat(), 200.0, -2.5, "alpaca:sip"
        ),
    )
    facts, missing = equity_quotes.fetch_equity_facts(date(2026, 9, 25))
    assert missing == ()
    msft = [fact for fact in facts if fact.id.startswith("equity.msft.")]
    assert {fact.source for fact in msft} == {"Alpaca SIP"}
    assert {fact.source_url for fact in msft} == {
        "https://docs.alpaca.markets/us/reference/stockbars"
    }


def test_equity_quotes_do_not_publish_stale_or_partial_symbol(monkeypatch):
    from daily_messenger.daily_report import equity_quotes

    monkeypatch.setattr(
        equity_quotes,
        "fetch_yahoo_daily_snapshot",
        lambda symbol, *, target_date: QuoteSnapshot(
            "2026-09-24" if symbol == "MSFT" else target_date.isoformat(),
            100.0,
            1.25,
            f"yahoo:{symbol}",
        ),
    )
    monkeypatch.setattr(equity_quotes, "resolve_api_key", lambda key: None)
    facts, missing = equity_quotes.fetch_equity_facts(date(2026, 9, 25))
    assert missing == ("MSFT",)
    assert not any(fact.id.startswith("equity.msft.") for fact in facts)


def test_invalid_yahoo_numbers_fall_back_to_alpaca_sip(monkeypatch):
    from daily_messenger.daily_report import equity_quotes

    monkeypatch.setattr(
        equity_quotes,
        "fetch_yahoo_daily_snapshot",
        lambda symbol, *, target_date: QuoteSnapshot(
            target_date.isoformat(), float("nan") if symbol == "MSFT" else 100.0, 1.0, "yahoo:test"
        ),
    )
    monkeypatch.setattr(equity_quotes, "resolve_api_key", lambda key: "test-key")
    monkeypatch.setattr(
        equity_quotes,
        "_fetch_alpaca_sip_snapshot",
        lambda symbol, report_date, key, secret: QuoteSnapshot(
            report_date.isoformat(), 200.0, -2.5, "alpaca:sip"
        ),
    )
    facts, missing = equity_quotes.fetch_equity_facts(date(2026, 9, 25))
    assert missing == ()
    assert {fact.source for fact in facts if fact.id.startswith("equity.msft.")} == {"Alpaca SIP"}


def test_alpaca_sip_snapshot_rejects_iex_and_stale_daily_bars(monkeypatch):
    from daily_messenger.daily_report import equity_quotes

    captured = {}

    def request_json(url, *, params, headers):
        captured["params"] = params
        return {
            "bars": {
                "MSFT": [
                    {"t": "2026-09-24T04:00:00Z", "c": 100},
                    {"t": "2026-09-25T04:00:00Z", "c": 101},
                ]
            }
        }

    monkeypatch.setattr(equity_quotes, "request_json", request_json)
    snapshot = equity_quotes._fetch_alpaca_sip_snapshot("MSFT", date(2026, 9, 25), "key", "secret")
    assert captured["params"]["feed"] == "sip"
    assert snapshot.change_pct == 1.0
    assert snapshot.day == "2026-09-25"
