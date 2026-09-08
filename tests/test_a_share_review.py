from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from a_share_daily import review


@pytest.fixture
def daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["600001.SH", "300001.SZ", "920001.BJ"],
            "pct_chg": [10.0, -20.0, 0.0],
            "amount": [100.0, 200.0, 50.0],
            "vol": [10.0, 20.0, 5.0],
            "open": [10.0, 10.0, 8.5],
            "high": [11.0, 10.0, 9.0],
            "low": [9.5, 8.0, 8.0],
            "close": [11.0, 8.0, 8.5],
            "pre_close": [10.0, 10.0, 8.5],
        }
    )


def test_market_overview_prefers_exchange_limit_prices(
    monkeypatch: pytest.MonkeyPatch, daily_frame: pd.DataFrame
) -> None:
    limit_status = pd.DataFrame(
        {
            "ts_code": ["600001.SH", "300001.SZ", "920001.BJ"],
            "up_limit": [11.0, 12.0, 11.0],
            "down_limit": [9.0, 8.0, 6.0],
        }
    )
    monkeypatch.setattr(review.D, "read_daily", lambda _date: daily_frame)
    monkeypatch.setattr(review.D, "read_limit_status", lambda _date: limit_status)

    result = review.load_market_overview("20260715")

    assert result["limit_up_count"] == 1
    assert result["down_limit_count"] == 1
    assert result["limit_count_method"] == "exchange_limit_price"


def test_market_overview_marks_percentage_fallback(
    monkeypatch: pytest.MonkeyPatch, daily_frame: pd.DataFrame
) -> None:
    monkeypatch.setattr(review.D, "read_daily", lambda _date: daily_frame)

    def unavailable(_date: str) -> pd.DataFrame:
        raise FileNotFoundError("limit status missing")

    monkeypatch.setattr(review.D, "read_limit_status", unavailable)

    result = review.load_market_overview("20260715")

    assert result["limit_up_count"] is None
    assert result["down_limit_count"] == 1
    assert result["limit_count_method"] == "pct_chg_approx"
    assert result["limit_count_error"] == "FileNotFoundError: limit status missing"


def test_previous_market_temperature_accepts_windows_utf8_bom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "history"
    archive.mkdir()
    payload = {"market_temperature": {"trade_date": "20260714", "heat_score": 52.0}}
    (archive / "evening_review_20260714.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8-sig",
    )
    monkeypatch.setenv("A_SHARE_EVENING_ARCHIVE_DIR", str(archive))

    result = review.load_previous_market_temperature("20260715")

    assert result == payload["market_temperature"]


def test_limit_analysis_keeps_missing_limit_up_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_date: str) -> pd.DataFrame:
        raise FileNotFoundError("limit data missing")

    monkeypatch.setattr(review.D, "read_limit_list", unavailable)
    monkeypatch.setattr(review.D, "read_limit_step", unavailable)

    result = review.load_limit_analysis(
        "20260715",
        overview={
            "limit_up_count": None,
            "down_limit_count": 2,
            "limit_count_method": "pct_chg_approx",
        },
    )

    assert result["limit_up"]["count"] is None
    assert result["limit_down"]["count"] == 2
