"""Reject ambiguous, incomplete and malformed provider reference windows."""

from datetime import UTC, datetime

import pytest

from daily_messenger.daily_report import gold_reference

START = datetime(2026, 9, 29, 20, tzinfo=UTC)
END = datetime(2026, 9, 30, 20, tzinfo=UTC)


@pytest.fixture
def provider(monkeypatch):
    payload = {
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 102.0,
        "highLowChangePercent": 7.14,
        "openCloseChangePercent": 2.0,
        "startTimestamp": 1790712000,
        "endTimestamp": 1790798400,
    }

    class Response:
        status_code = 200

        def json(self):
            return payload

    def get(url, *, params, headers, timeout, allow_redirects):
        assert url == "https://api.gold-api.com/ohlc/XAU"
        assert params == {"startTimestamp": 1790712000, "endTimestamp": 1790798400}
        assert headers == {"x-api-key": "test-key"}
        assert timeout == 12
        assert allow_redirects is False
        return Response()

    monkeypatch.setattr(gold_reference.requests, "get", get)
    return payload


def test_preserves_window_without_claiming_actual_quote_time(provider):
    row = gold_reference.fetch_reference_window("XAU", START, END, "test-key")
    assert row.close == 102.0
    assert row.start == START and row.end == END
    assert row.symbol == "XAU"
    assert row.actual_quote_time is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("close", float("nan")),
        ("close", 10**400),
        ("close", float("inf")),
        ("close", -1),
        ("close", True),
        ("close", 0),
        ("close", 106.0),
        ("high", 97.0),
        ("open", "100"),
        ("endTimestamp", 1790798399),
        ("startTimestamp", "1790712000"),
    ],
)
def test_rejects_bad_price_or_mismatched_window(provider, field, value):
    provider[field] = value
    with pytest.raises(RuntimeError, match="invalid"):
        gold_reference.fetch_reference_window("XAU", START, END, "test-key")


def test_future_window_is_rejected_before_request(provider, monkeypatch):
    monkeypatch.setattr(
        gold_reference.requests, "get", lambda *a, **kw: pytest.fail("unexpected request")
    )
    with pytest.raises(ValueError, match="complete"):
        gold_reference.fetch_reference_window(
            "XAU",
            datetime(2099, 1, 1, tzinfo=UTC),
            datetime(2099, 1, 2, tzinfo=UTC),
            "test-key",
        )


@pytest.mark.parametrize(
    "symbol,key", [("GC=F", "test-key"), ("XAU", ""), ("XAU", " YOUR_GOLD_API_KEY ")]
)
def test_rejects_unknown_symbol_or_empty_key(provider, symbol, key):
    with pytest.raises(ValueError):
        gold_reference.fetch_reference_window(symbol, START, END, key)


@pytest.mark.parametrize("status", [301, 401, 429, 500])
def test_reports_only_status_without_response_body(monkeypatch, status):
    class Response:
        status_code = status
        text = "secret-response-body"

    monkeypatch.setattr(gold_reference.requests, "get", lambda *a, **kw: Response())
    with pytest.raises(RuntimeError, match=f"^Gold API HTTP {status}$"):
        gold_reference.fetch_reference_window("XAG", START, END, "test-key")


def test_network_error_does_not_expose_request_credentials(monkeypatch):
    def fail(*args, **kwargs):
        raise gold_reference.requests.ConnectionError("test-key-secret")

    monkeypatch.setattr(gold_reference.requests, "get", fail)
    with pytest.raises(RuntimeError, match="^Gold API request failed$") as raised:
        gold_reference.fetch_reference_window("XAU", START, END, "test-key")
    assert raised.value.__suppress_context__ is True


@pytest.mark.parametrize(
    "start,end",
    [
        (START.replace(tzinfo=None), END),
        (END, START),
        (END, END),
        (START, END.replace(microsecond=1)),
    ],
)
def test_invalid_boundaries_do_not_reach_provider(provider, start, end, monkeypatch):
    monkeypatch.setattr(
        gold_reference.requests, "get", lambda *a, **kw: pytest.fail("unexpected request")
    )
    with pytest.raises(ValueError):
        gold_reference.fetch_reference_window("XAU", start, end, "test-key")


@pytest.mark.parametrize(
    "body", [None, [], {}, {"startTimestamp": 1790712000, "endTimestamp": 1790798400}]
)
def test_rejects_incomplete_or_non_object_payload(monkeypatch, body):
    class Response:
        status_code = 200

        def json(self):
            return body

    monkeypatch.setattr(gold_reference.requests, "get", lambda *a, **kw: Response())
    with pytest.raises(RuntimeError, match="invalid"):
        gold_reference.fetch_reference_window("XAG", START, END, "test-key")


def test_rejects_non_json_without_exposing_body(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            raise ValueError("secret-body")

    monkeypatch.setattr(gold_reference.requests, "get", lambda *a, **kw: Response())
    with pytest.raises(RuntimeError, match="^Gold API JSON invalid$"):
        gold_reference.fetch_reference_window("XAU", START, END, "test-key")


def test_successful_silver_request_uses_distinct_symbol(provider, monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return provider

    def get(url, **kwargs):
        assert url == "https://api.gold-api.com/ohlc/XAG"
        return Response()

    monkeypatch.setattr(gold_reference.requests, "get", get)
    assert gold_reference.fetch_reference_window("XAG", START, END, "test-key").symbol == "XAG"
