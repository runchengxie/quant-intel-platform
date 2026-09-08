"""覆盖率测试：提升 crypto/klines 的分支覆盖率，以便解除 coverage.omit。

聚焦纯函数与三个交易所的解析路径，网络请求一律 monkeypatch requests.get。
不触碰 init_history / incremental_fetch 的联网编排（含 time.sleep）。
"""

import pandas as pd
import pytest

from daily_messenger.crypto import klines


def test_parse_lookback_units():
    assert klines.parse_lookback("7d") == pd.Timedelta(days=7)
    assert klines.parse_lookback("12h") == pd.Timedelta(hours=12)
    assert klines.parse_lookback("30m") == pd.Timedelta(minutes=30)


def test_parse_lookback_invalid_unit():
    with pytest.raises(ValueError):
        klines.parse_lookback("5w")


def test_daterange_inclusive():
    start = pd.Timestamp("2026-01-01", tz="UTC").to_pydatetime()
    end = pd.Timestamp("2026-01-03", tz="UTC").to_pydatetime()
    days = list(klines.daterange(start, end))
    assert len(days) == 3
    assert days[0] == start
    assert days[-1] == end


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


def test_fetch_binance_empty(monkeypatch):
    monkeypatch.setattr(
        klines.requests,
        "get",
        lambda *a, **k: _FakeResponse([]),
    )
    df = klines.fetch_binance("BTCUSDT", "1h", 0, 1000)
    assert df.empty


def test_fetch_binance_parses_rows(monkeypatch):
    rows = [
        [
            1700000000000,
            "100",
            "110",
            "90",
            "105",
            "1.0",
            1700000000999,
            "0",
            "10",
            "0.1",
            "0.2",
            "ignore",
        ],
        [
            1700000060000,
            "105",
            "115",
            "95",
            "108",
            "2.0",
            1700000060999,
            "0",
            "12",
            "0.3",
            "0.4",
            "ignore",
        ],
    ]
    monkeypatch.setattr(
        klines.requests,
        "get",
        lambda *a, **k: _FakeResponse(rows),
    )
    df = klines.fetch_binance("BTCUSDT", "1h", 0, 2000000000000)
    assert len(df) == 2
    assert df["symbol"].iloc[0] == "BTCUSDT"
    assert df["interval"].iloc[0] == "1h"
    assert float(df["close"].iloc[0]) == 105.0
    assert "ignore" not in df.columns


def test_fetch_kraken_parses_rows(monkeypatch):
    payload = {
        "result": {
            "XXBTZUSD": [
                [1700000000, "100", "110", "90", "105", "1.0", "2.0", 10],
            ],
            "last": "1700000000",
        },
        "error": [],
    }
    monkeypatch.setattr(klines.requests, "get", lambda *a, **k: _FakeResponse(payload))
    df = klines.fetch_kraken(60, 1700000000)
    assert len(df) == 1
    assert df["symbol"].iloc[0] == "XBTUSD"
    assert float(df["close"].iloc[0]) == 105.0


def test_fetch_kraken_empty(monkeypatch):
    payload = {"result": {"XXBTZUSD": [], "last": "1700000000"}, "error": []}
    monkeypatch.setattr(klines.requests, "get", lambda *a, **k: _FakeResponse(payload))
    df = klines.fetch_kraken(60, 1700000000)
    assert df.empty


def test_fetch_bitstamp_parses_rows(monkeypatch):
    payload = {
        "data": {
            "ohlc": [
                {
                    "timestamp": "1700000000",
                    "open": "100",
                    "high": "110",
                    "low": "90",
                    "close": "105",
                    "volume": "1.0",
                },
            ]
        }
    }
    monkeypatch.setattr(klines.requests, "get", lambda *a, **k: _FakeResponse(payload))
    df = klines.fetch_bitstamp(3600, 1700000000, 1700000000)
    assert len(df) == 1
    assert df["symbol"].iloc[0] == "BTCUSD"
    assert float(df["close"].iloc[0]) == 105.0


def test_fetch_bitstamp_empty(monkeypatch):
    empty = {"data": {"ohlc": []}}
    monkeypatch.setattr(klines.requests, "get", lambda *a, **k: _FakeResponse(empty))
    df = klines.fetch_bitstamp(3600, 1700000000, 1700000000)
    assert df.empty


def test_init_history_rejects_bad_interval(tmp_path):
    with pytest.raises(ValueError):
        klines.init_history(
            symbol="BTCUSDT",
            interval="9z",
            start=pd.Timestamp("2026-01-01", tz="UTC").to_pydatetime(),
            end=pd.Timestamp("2026-01-02", tz="UTC").to_pydatetime(),
            outdir=tmp_path,
        )


def test_incremental_fetch_rejects_bad_interval(tmp_path):
    with pytest.raises(ValueError):
        klines.incremental_fetch(interval="9z", outdir=tmp_path)


def test_run_init_history_argparse(tmp_path, monkeypatch):
    # 桩掉 fetch_one 避免真实网络；无数据分支仍返回 0
    monkeypatch.setattr(klines, "fetch_one", lambda *a, **k: pd.DataFrame())
    rc = klines.run_init_history(
        [
            "--symbol",
            "BTCUSDT",
            "--interval",
            "1d",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-01",
            "--outdir",
            str(tmp_path),
        ]
    )
    assert rc == 0


def test_run_fetch_argparse(tmp_path, monkeypatch):
    # 桩掉三个交易所抓取，避免真实网络
    monkeypatch.setattr(klines, "fetch_binance", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(klines, "fetch_kraken", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(klines, "fetch_bitstamp", lambda *a, **k: pd.DataFrame())
    rc = klines.run_fetch(
        [
            "--interval",
            "1d",
            "--outdir",
            str(tmp_path),
            "--lookback",
            "1d",
            "--max-pages",
            "1",
        ]
    )
    assert rc == 0
