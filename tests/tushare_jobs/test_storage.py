from datetime import date

import pandas as pd

from tushare_jobs.storage import DataStore


def test_store_and_consolidate(tmp_path):
    store = DataStore(base_dir=tmp_path, file_format="csv")
    df1 = pd.DataFrame({"ts_code": ["000001.SZ"], "float_date": ["20240101"]})
    df2 = pd.DataFrame({"ts_code": ["000002.SZ"], "float_date": ["20240102"]})

    store.save_raw_window("share_float", date(2024, 1, 1), date(2024, 1, 1), df1)
    store.save_raw_window("share_float", date(2024, 1, 2), date(2024, 1, 2), df2)

    merged = store.consolidate("share_float", ["ts_code", "float_date"])
    assert len(merged) == 2
