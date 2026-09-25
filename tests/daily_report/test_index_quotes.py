from datetime import date

from daily_messenger.etl.types import QuoteSnapshot


def test_index_quotes_require_all_four_completed_same_day_bars(monkeypatch):
    from daily_messenger.daily_report.index_quotes import fetch_index_facts

    snapshots = {
        "^GSPC": QuoteSnapshot("2026-09-25", 7704.13, -0.02, "yahoo:^GSPC"),
        "^DJI": QuoteSnapshot("2026-09-25", 51349.98, -0.31, "yahoo:^DJI"),
        "^IXIC": QuoteSnapshot("2026-09-25", 26939.37, 0.01, "yahoo:^IXIC"),
        "^RUT": QuoteSnapshot("2026-09-25", 2600.0, 0.42, "yahoo:^RUT"),
    }
    monkeypatch.setattr(
        "daily_messenger.daily_report.index_quotes.fetch_yahoo_daily_snapshot",
        lambda symbol, *, target_date: (
            snapshots[symbol] if target_date == date(2026, 9, 25) else None
        ),
    )

    facts, missing = fetch_index_facts(date(2026, 9, 25))

    assert missing == ()
    assert len(facts) == 4
    assert {fact.id for fact in facts} == {
        "index.spx.change_percent",
        "index.dow.change_percent",
        "index.nasdaq.change_percent",
        "index.russell2000.change_percent",
    }
    assert facts[0].value == -0.02
    assert facts[0].observation_date == "2026-09-25"
    assert facts[0].source_url == "https://finance.yahoo.com/quote/%5EGSPC/history/"
    assert all(fact.quality == "ok" for fact in facts)


def test_index_quotes_do_not_publish_partial_set(monkeypatch):
    from daily_messenger.daily_report.index_quotes import fetch_index_facts

    def fetch(symbol, *, target_date):
        assert target_date == date(2026, 9, 25)
        if symbol == "^IXIC":
            raise RuntimeError("provider unavailable")
        day = "2026-09-24" if symbol == "^RUT" else "2026-09-25"
        return QuoteSnapshot(day, 100.0, 1.0, f"yahoo:{symbol}")

    monkeypatch.setattr(
        "daily_messenger.daily_report.index_quotes.fetch_yahoo_daily_snapshot", fetch
    )

    facts, missing = fetch_index_facts(date(2026, 9, 25))

    assert facts == []
    assert missing == ("^IXIC", "^RUT")
