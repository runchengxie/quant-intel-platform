from datetime import date

import pandas as pd

from tushare_jobs import listed_company
from tushare_jobs.listed_company import ListedCompanyFetcher
from tushare_jobs.storage import DataStore


class ImmediateRunner:
    def call(self, _label, fn):
        return fn()


def test_share_float_uses_single_mdp_slice_without_upstream_autosplit(monkeypatch, tmp_path):
    frame = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "ann_date": "20240103",
                "float_date": "20240201",
                "holder_name": "holder",
                "share_type": "A",
            }
        ]
    )
    monkeypatch.setattr(
        listed_company,
        "load_mdp_asset",
        lambda _dataset: (frame, tmp_path / "share_float.parquet"),
    )
    store = DataStore(base_dir=tmp_path / "store", file_format="csv")
    fetcher = ListedCompanyFetcher(object(), ImmediateRunner(), store)

    summary = fetcher.fetch_share_float(
        start=date(2024, 1, 1),
        end=date(2024, 1, 7),
        window="week",
        resume=False,
        force=True,
        threshold=5,
    )

    assert summary.windows == 1
    assert summary.rows == 1
    path = store.raw_window_path("share_float", date(2024, 1, 1), date(2024, 1, 7))
    assert path.exists()
