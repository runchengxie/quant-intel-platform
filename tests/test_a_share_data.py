from __future__ import annotations

import pandas as pd
import pytest

from a_share_daily import data


def test_exact_limit_counts_use_exchange_prices_for_each_board() -> None:
    daily = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "300001.SZ", "920001.BJ", "000002.SZ"],
            "close": [11.0, 8.0, 8.5, 9.51],
        }
    )
    limit_status = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "300001.SZ", "920001.BJ", "000002.SZ"],
            "up_limit": [11.0, 12.0, 13.0, 11.0],
            "down_limit": [9.0, 8.0, 7.0, 9.0],
        }
    )

    assert data.get_exact_limit_counts(daily, limit_status) == (1, 1)


def test_exact_limit_counts_reject_ambiguous_inputs() -> None:
    daily = pd.DataFrame({"ts_code": ["000001.SZ"]})
    limit_status = pd.DataFrame({"ts_code": ["000001.SZ"], "up_limit": [11.0], "down_limit": [9.0]})

    try:
        data.get_exact_limit_counts(daily, limit_status)
    except ValueError as exc:
        assert "close" in str(exc)
    else:
        raise AssertionError("missing close column must be rejected")


def test_exact_limit_counts_reject_partial_limit_status() -> None:
    daily = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "close": [11.0, 9.0],
        }
    )
    limit_status = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "up_limit": [11.0],
            "down_limit": [9.0],
        }
    )

    with pytest.raises(ValueError, match="coverage too low"):
        data.get_exact_limit_counts(daily, limit_status)
