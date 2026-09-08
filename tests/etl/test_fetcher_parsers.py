from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from daily_messenger.etl.fetchers import ai_news, edgar, fmp


def test_ai_news_extractors_and_trading_date() -> None:
    gemini_payload = {"candidates": [{"content": {"parts": [{"text": "  <news>- ok</news>  "}]}}]}
    glm_payload = {"choices": [{"message": {"content": [{"text": "glm text"}]}}]}

    assert ai_news._extract_gemini_text(gemini_payload) == "<news>- ok</news>"
    assert ai_news._extract_glm_text(glm_payload) == "glm text"

    spec = ai_news.AI_NEWS_MARKET_SPECS[0]
    target = ai_news._resolve_market_trading_date(
        datetime(2024, 4, 1, 12, 0, tzinfo=ZoneInfo("UTC")),
        spec,
    )
    assert target.weekday() < 5


def test_glm_direct_connection_disables_requests_env_proxy(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request_json(url: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"url": url, **kwargs})
        return {"choices": [{"message": {"content": "<news>- ok</news>"}}]}

    monkeypatch.setattr(ai_news, "_request_json", fake_request_json)

    ai_news._call_glm_chat_completions(
        "glm-test",
        "key",
        "prompt",
        True,
        5.0,
        "enabled",
        True,
    )

    assert calls[0]["trust_env"] is False
    assert calls[0]["json_body"]["tools"][0]["type"] == "web_search"


def test_fmp_extracts_metrics_and_fetches_fundamentals(monkeypatch) -> None:
    payloads: dict[str, Any] = {
        "AAA": [{"date": "2024-01-01", "revenueTTM": 1000, "netIncomeTTM": 100}],
        "BBB": [{"date": "2024-01-01", "weightedAverageShsOutDilTTM": 10}],
    }

    def fake_request(url: str, *, params: dict[str, Any]) -> Any:
        ticker = str(params["symbol"])
        if url.endswith("/ratios-ttm"):
            return []
        return payloads[ticker]

    monkeypatch.setattr(fmp, "_request_json", fake_request)
    monkeypatch.setattr(fmp, "_sleep", lambda seconds: None)

    results, errors = fmp._fetch_fmp_fundamentals(["AAA", "BBB"], "key")

    assert not errors
    assert results["AAA"]["revenue_ttm"] == 1000.0
    assert results["AAA"]["net_income_ttm"] == 100.0
    assert results["BBB"]["shares_diluted_latest"] == 10.0


def test_fmp_extracts_stable_metric_ratios() -> None:
    metrics = fmp._extract_fmp_metrics(
        [{"symbol": "AAA", "marketCap": 1000.0}],
        [
            {
                "symbol": "AAA",
                "priceToEarningsRatioTTM": 10.0,
                "priceToSalesRatioTTM": 2.0,
                "priceToBookRatioTTM": 4.0,
            }
        ],
    )

    assert metrics["market_cap"] == 1000.0
    assert metrics["net_income_ttm"] == 100.0
    assert metrics["revenue_ttm"] == 500.0
    assert metrics["equity_latest"] == 250.0
    assert metrics["pe_ttm"] == 10.0


def test_fmp_theme_metrics_with_injected_price_only_and_fundamentals(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PREFER_STOOQ", "1")

    dependencies = fmp.ThemeMetricDependencies(
        yahoo_allowed=lambda: False,
        fetch_yahoo_quotes=lambda symbols: {},
        fetch_price_only_quotes=lambda symbols, api_keys=None: {
            "AAA": {
                "changesPercentage": 2.0,
                "price": 20.0,
                "marketCap": None,
                "source": "stooq",
            },
            "BBB": {
                "changesPercentage": -1.0,
                "price": 30.0,
                "marketCap": None,
                "source": "alpaca",
            },
        },
        fetch_edgar_fundamentals=lambda symbols: (
            {
                "AAA": {
                    "net_income_ttm": 100.0,
                    "revenue_ttm": 1000.0,
                    "shares_diluted_latest": 10.0,
                    "equity_latest": 500.0,
                },
                "BBB": {
                    "net_income_ttm": 150.0,
                    "revenue_ttm": 1200.0,
                    "shares_diluted_latest": 20.0,
                    "equity_latest": 800.0,
                },
            },
            [],
            [],
        ),
    )

    themes, status = fmp._fetch_theme_metrics_from_fmp(
        {},
        dependencies,
        theme_symbols={"ai": ["AAA", "BBB"]},
    )

    assert status.ok
    assert themes["ai"]["change_pct"] == 0.5
    assert themes["ai"]["market_cap"] == 800.0
    assert themes["ai"]["symbols"][0]["pe"] == 2.0


def test_fmp_theme_metrics_uses_fmp_fundamental_fallback(monkeypatch) -> None:
    dependencies = fmp.ThemeMetricDependencies(
        yahoo_allowed=lambda: True,
        fetch_yahoo_quotes=lambda symbols: {
            "AAA": {
                "changesPercentage": 1.0,
                "price": 50.0,
                "marketCap": None,
                "pe": None,
                "priceToSalesRatioTTM": None,
            }
        },
        fetch_price_only_quotes=lambda symbols, api_keys=None: {},
        fetch_edgar_fundamentals=lambda symbols: ({}, ["AAA"], []),
    )
    monkeypatch.setattr(
        fmp,
        "_fetch_fmp_fundamentals",
        lambda symbols, api_key: (
            {
                "AAA": {
                    "net_income_ttm": 25.0,
                    "revenue_ttm": 500.0,
                    "shares_diluted_latest": 10.0,
                    "equity_latest": 200.0,
                }
            },
            [],
        ),
    )

    themes, status = fmp._fetch_theme_metrics_from_fmp(
        {"financial_modeling_prep": "key"},
        dependencies,
        theme_symbols={"ai": ["AAA"]},
    )

    assert status.ok
    assert themes["ai"]["avg_pe"] == 20.0
    assert themes["ai"]["avg_ps"] == 1.0
    assert "FMP" in status.message


def test_edgar_extracts_metrics_from_companyfacts() -> None:
    facts = {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"end": "2024-03-31", "val": 100, "form": "10-Q", "fp": "Q1"},
                        {"end": "2023-12-31", "val": 200, "form": "10-Q", "fp": "Q4"},
                        {"end": "2023-09-30", "val": 300, "form": "10-Q", "fp": "Q3"},
                        {"end": "2023-06-30", "val": 400, "form": "10-Q", "fp": "Q2"},
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {"end": "2024-03-31", "val": 10, "form": "10-Q", "fp": "Q1"},
                        {"end": "2023-12-31", "val": 20, "form": "10-Q", "fp": "Q4"},
                        {"end": "2023-09-30", "val": 30, "form": "10-Q", "fp": "Q3"},
                        {"end": "2023-06-30", "val": 40, "form": "10-Q", "fp": "Q2"},
                    ]
                }
            },
            "WeightedAverageNumberOfDilutedSharesOutstanding": {
                "units": {"shares": [{"end": "2024-03-31", "val": 10, "form": "10-Q", "fp": "Q1"}]}
            },
            "StockholdersEquity": {
                "units": {"USD": [{"end": "2024-03-31", "val": 500, "form": "10-Q", "fp": "Q1"}]}
            },
        }
    }

    metrics = edgar._extract_edgar_metrics(facts)

    assert metrics["revenue_ttm"] == 1000.0
    assert metrics["net_income_ttm"] == 100.0
    assert metrics["shares_diluted_latest"] == 10.0
    assert metrics["equity_latest"] == 500.0


def test_edgar_fundamentals_and_healthcheck(monkeypatch) -> None:
    class DummySession:
        closed = False

        def close(self) -> None:
            self.closed = True

    session = DummySession()
    monkeypatch.setattr(edgar, "_init_edgar_session", lambda: session)
    monkeypatch.setattr(edgar, "_load_edgar_ticker_mapping", lambda session: {"AAA": "1"})
    monkeypatch.setattr(
        edgar,
        "_fetch_edgar_companyfacts",
        lambda session, cik: {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "end": "2024-03-31",
                                "val": 100,
                                "form": "10-K",
                                "fp": "FY",
                            }
                        ]
                    }
                }
            }
        },
    )

    results, missing, errors = edgar._fetch_edgar_fundamentals(["AAA", "BBB"])
    status = edgar._edgar_healthcheck()

    assert "AAA" in results
    assert missing == ["BBB"]
    assert not errors
    assert status.ok
    assert session.closed
