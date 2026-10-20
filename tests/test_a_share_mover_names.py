import hashlib
import json

import pandas as pd
import pytest

from a_share_daily import data


@pytest.mark.parametrize("invalid", ["hash", "future", "quality", "absent", "valid"])
def test_stock_names_require_owner_receipt(tmp_path, monkeypatch, invalid):
    monkeypatch.setattr(data, "_data_root", lambda: tmp_path)
    folder = tmp_path / "instruments"
    folder.mkdir()
    path = folder / "a_share_all_instruments_latest.parquet"
    pd.DataFrame(
        {
            "ts_code": ["A", "B", "B", "C", "D", "A"],
            "name": ["Alpha", "One", "Two", None, "  ", "Alpha"],
        }
    ).to_parquet(path)
    receipt = {
        "schema_version": "market-data-platform.tushare-reference.v1",
        "dataset": "instruments",
        "quality_status": "complete",
        "target_date": "20260928",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    if invalid == "hash":
        receipt["sha256"] = "bad"
    if invalid == "future":
        receipt["target_date"] = "20261021"
    if invalid == "quality":
        receipt["quality_status"] = "partial"
    if invalid != "absent":
        path.with_suffix(".receipt.json").write_text(json.dumps(receipt))
    assert data.read_stock_names("20261020") == ({"A": "Alpha"} if invalid == "valid" else {})


def test_stock_names_without_config_remain_optional(monkeypatch):
    monkeypatch.delenv("DATA_PLATFORM_ROOT", raising=False)
    monkeypatch.delenv("MDP_FALLBACK_ROOT", raising=False)
    assert data.read_stock_names("20261020") == {}
