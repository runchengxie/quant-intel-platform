from datetime import date

import pytest

from daily_messenger.daily_report import index_quotes
from daily_messenger.daily_report.provider_diagnostics import failure_reason


@pytest.mark.parametrize(
    "exception,reason",
    [
        (RuntimeError("HTTP 状态错误: 403 secret-api-response"), "http_403"),
        (TimeoutError("secret-url"), "timeout"),
        (RuntimeError("Yahoo Finance 最新日线尚未完成"), "bar_incomplete"),
        (
            RuntimeError("Yahoo Finance 指定交易日日线不存在或重复"),
            "target_bar_missing_or_duplicate",
        ),
        (ValueError("secret-value"), "invalid_data"),
    ],
)
def test_reason_contains_no_provider_body(exception, reason):
    assert failure_reason(exception) == reason


def test_index_failure_logs_reason_but_never_response_body(monkeypatch, caplog):
    def failed(*args, **kwargs):
        raise RuntimeError("HTTP 状态错误: 403 secret-api-response")

    monkeypatch.setattr(index_quotes, "fetch_yahoo_daily_snapshot", failed)
    facts, missing = index_quotes.fetch_index_facts(date(2026, 9, 30))
    assert not facts and len(missing) == 4
    assert "http_403" in caplog.text
    assert "secret-api-response" not in caplog.text
