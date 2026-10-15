import pandas as pd

from a_share_daily.review.loaders import _return_distribution


def test_return_distribution_covers_ipo_outliers_boundaries_and_empty_buckets():
    counts = _return_distribution(pd.Series([-100.0, -9.9, 0.0, 9.9, 100.0, 401.7143]))
    assert len(counts) == 12
    assert counts["-inf~-9.9%"] == 1
    assert counts["-9.9~-7%"] == 1
    assert counts["0~1%"] == 1
    assert counts["9.9~inf%"] == 3
    assert counts["1~3%"] == 0
    assert sum(counts.values()) == 6


def test_return_distribution_does_not_fabricate_missing_returns():
    counts = _return_distribution(pd.Series([float("nan"), float("inf"), -float("inf"), 0.0]))
    assert sum(counts.values()) == 1
    assert counts["0~1%"] == 1


def test_nullable_provider_returns_remain_explicitly_missing():
    counts = _return_distribution(pd.Series([pd.NA, 401.7143], dtype="Float64"))
    assert sum(counts.values()) == 1
    assert counts["9.9~inf%"] == 1
