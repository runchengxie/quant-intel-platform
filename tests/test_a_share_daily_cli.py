from __future__ import annotations

import sys

import pytest

from a_share_daily import cli


@pytest.mark.parametrize(
    "args, expected",
    [
        (["--help"], "A-share daily report pipeline"),
        (["morning", "--help"], "Trade date YYYYMMDD"),
        (["morning-report", "--help"], "--manifest"),
        (["daily-watch20", "--help"], "--source-date"),
        (["review", "--help"], "--json"),
        (["doctor", "--help"], "--live"),
        (["cashflow-delivery", "--help"], "--selection"),
        (["weekly-basket", "--help"], "--as-of-date"),
    ],
)
def test_a_share_daily_help_smoke(
    args: list[str],
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["a-share-daily", *args])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    assert expected in capsys.readouterr().out


def test_feishu_chat_id_has_no_hardcoded_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_INTEL_INTERNAL_CHAT_ID", raising=False)
    monkeypatch.delenv("MARKET_INTEL_CLIENT_CHAT_ID", raising=False)
    monkeypatch.delenv("A_SHARE_FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_CHAT_ID", raising=False)

    assert cli._default_feishu_chat_id() == ""


def test_require_feishu_chat_id_fails_without_configuration(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli._require_feishu_chat_id(" ")

    assert exc_info.value.code == 1
    assert "MARKET_INTEL_INTERNAL_CHAT_ID" in capsys.readouterr().err
