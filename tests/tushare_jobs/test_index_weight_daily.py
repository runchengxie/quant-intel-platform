from datetime import date

import pandas as pd
import pytest

from tushare_jobs.index_weight_daily import expand_index_weight_daily
from tushare_jobs.stock_st import has_data_rows


def test_has_data_rows(tmp_path):
    path = tmp_path / "file.csv"

    assert has_data_rows(path) is False

    path.write_text("a,b\n", encoding="utf-8")
    assert has_data_rows(path) is False

    path.write_text("a,b\n1,2\n", encoding="utf-8")
    assert has_data_rows(path) is True


def test_expand_index_weight_daily_generates_segments_and_drift(tmp_path):
    df = pd.DataFrame(
        [
            {
                "trade_date": "20250228",
                "index_code": "000300.SH",
                "con_code": "A",
                "weight": 0.6,
            },
            {
                "trade_date": "20250228",
                "index_code": "000300.SH",
                "con_code": "B",
                "weight": 0.4,
            },
            {
                "trade_date": "20250331",
                "index_code": "000300.SH",
                "con_code": "A",
                "weight": 0.7,
            },
            {
                "trade_date": "20250331",
                "index_code": "000300.SH",
                "con_code": "C",
                "weight": 0.3,
            },
        ]
    )

    trade_dates = [
        date(2025, 2, 28),
        date(2025, 3, 3),
        date(2025, 3, 4),
        date(2025, 3, 31),
    ]

    prices = pd.DataFrame(
        [
            {"ts_code": "A", "trade_date": "20250228", "close": 10},
            {"ts_code": "B", "trade_date": "20250228", "close": 20},
            {"ts_code": "C", "trade_date": "20250228", "close": 30},
            {"ts_code": "A", "trade_date": "20250303", "close": 11},
            {"ts_code": "B", "trade_date": "20250303", "close": 19},
            {"ts_code": "C", "trade_date": "20250303", "close": 31},
            {"ts_code": "A", "trade_date": "20250304", "close": 12},
            {"ts_code": "B", "trade_date": "20250304", "close": 22},
            {"ts_code": "C", "trade_date": "20250304", "close": 32},
            {"ts_code": "A", "trade_date": "20250331", "close": 13},
            {"ts_code": "B", "trade_date": "20250331", "close": 23},
            {"ts_code": "C", "trade_date": "20250331", "close": 34},
        ]
    )

    out_path = tmp_path / "daily.csv"
    rows = expand_index_weight_daily(
        df=df, trade_dates=trade_dates, output_path=out_path, prices=prices
    )
    out_df = pd.read_csv(out_path)

    assert rows == 8
    assert len(out_df) == 8

    march3 = out_df[out_df["trade_date"] == "2025-03-03"]
    assert set(march3["snapshot_date"]) == {"2025-02-28"}
    assert set(march3["con_code"]) == {"A", "B"}

    march31 = out_df[out_df["trade_date"] == "2025-03-31"]
    assert set(march31["snapshot_date"]) == {"2025-03-31"}
    assert set(march31["con_code"]) == {"A", "C"}
    march31_weights = march31.set_index("con_code")["drift_weight"].to_dict()
    assert march31_weights["A"] == pytest.approx(0.7, rel=1e-5)
    assert march31_weights["C"] == pytest.approx(0.3, rel=1e-5)

    drift = (
        out_df[out_df["trade_date"] == "2025-03-04"].set_index("con_code")["drift_weight"].to_dict()
    )
    assert drift["A"] == pytest.approx(0.62069, rel=1e-4)
    assert drift["B"] == pytest.approx(0.37931, rel=1e-4)
