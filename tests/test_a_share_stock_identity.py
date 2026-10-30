"""Stock display identity retains validated names and exchange-qualified codes."""

import pandas as pd

from a_share_daily.review import loaders, renderers


def test_turnover_keeps_row_names_then_validated_reference_names(monkeypatch):
    frame = pd.DataFrame(
        [
            {
                "ts_code": "300308.SZ",
                "name": " 行内 名称 ",
                "amount": 300000,
                "pct_chg": 1,
                "close": 20,
            },
            {"ts_code": "600000.SH", "name": None, "amount": 200000, "pct_chg": -2, "close": 10},
            {"ts_code": "000001.SZ", "name": "", "amount": 100000, "pct_chg": 0, "close": 5},
        ]
    )
    monkeypatch.setattr(loaders.D, "read_daily", lambda _: frame)
    monkeypatch.setattr(
        loaders.D, "read_stock_names", lambda _: {"300308.SZ": "参考名称", "600000.SH": "浦发银行"}
    )
    result = loaders.load_top_amount_stocks("20261029")
    assert list(result["name"]) == ["行内 名称", "浦发银行", ""]
    assert list(result["ts_code"]) == list(frame["ts_code"])
    assert list(result["amount_yi"]) == [3, 2, 1]
    markdown = "\n".join(renderers._render_top_amount_section(result))
    assert "| 名称 | 代码 | 成交额(亿) | 涨跌 |" in markdown
    assert "| 行内 名称 | 300308.SZ | 3.0 | +1.00% |" in markdown
    assert "| 浦发银行 | 600000.SH |" in markdown
    assert "| N/A | 000001.SZ |" in markdown
