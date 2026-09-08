from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from research_contracts import file_sha256
from tushare_jobs import index_weight, listed_company, stock_st
from tushare_jobs.listed_company import ListedCompanyFetcher
from tushare_jobs.storage import (
    DataStore,
    ReferenceAssetUnavailable,
    load_mdp_asset,
)


class ImmediateRunner:
    def call(self, _label, fn):
        return fn()


def test_load_mdp_asset_validates_receipt(monkeypatch, tmp_path) -> None:
    path = tmp_path / "assets/tushare/a_share/stock_st/a_share_all_stock_st_latest.parquet"
    path.parent.mkdir(parents=True)
    expected = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20260729"}])
    expected.to_parquet(path, index=False)
    receipt = {
        "schema_version": "market-data-platform.tushare-reference.v1",
        "dataset": "stock_st",
        "rows": 1,
        "sha256": file_sha256(path),
        "quality_status": "complete",
    }
    path.with_suffix(".receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setenv("DATA_PLATFORM_ROOT", str(tmp_path))

    actual, source = load_mdp_asset("stock_st")

    pd.testing.assert_frame_equal(actual, expected)
    assert source == path


def test_load_mdp_asset_rejects_checksum_mismatch(monkeypatch, tmp_path) -> None:
    path = tmp_path / "assets/tushare/a_share/stock_st/a_share_all_stock_st_latest.parquet"
    path.parent.mkdir(parents=True)
    pd.DataFrame([{"ts_code": "000001.SZ"}]).to_parquet(path, index=False)
    path.with_suffix(".receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "market-data-platform.tushare-reference.v1",
                "dataset": "stock_st",
                "rows": 1,
                "sha256": "bad",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DATA_PLATFORM_ROOT", str(tmp_path))

    with pytest.raises(ReferenceAssetUnavailable, match="checksum mismatch"):
        load_mdp_asset("stock_st")


def test_index_weight_does_not_write_partial_mdp_result(monkeypatch, tmp_path) -> None:
    raw = pd.DataFrame(
        [{"index_code": "000300.SH", "con_code": "000001.SZ", "trade_date": "20260729"}]
    )

    def load(dataset):
        if dataset == "index_weight":
            return raw, tmp_path / "raw.parquet"
        raise ReferenceAssetUnavailable("daily unpublished")

    monkeypatch.setattr(index_weight, "load_mdp_asset", load)

    with pytest.raises(ReferenceAssetUnavailable, match="daily unpublished"):
        index_weight._try_consume_mdp_index_weight(
            "000300.SH",
            data_dir=tmp_path,
            generate_daily=True,
        )

    assert not (tmp_path / "index_weight/index_weight_000300_SH.csv").exists()


def test_index_weight_consumes_complete_mdp_pair(monkeypatch, tmp_path) -> None:
    raw = pd.DataFrame(
        [{"index_code": "000300.SH", "con_code": "000001.SZ", "trade_date": "20260729"}]
    )
    daily = raw.assign(snapshot_date="20260729")

    def load(dataset):
        frame = raw if dataset == "index_weight" else daily
        return frame, tmp_path / f"{dataset}.parquet"

    monkeypatch.setattr(index_weight, "load_mdp_asset", load)

    result = index_weight.refresh_index_weight(
        SimpleNamespace(),
        "000300.SH",
        data_dir=tmp_path,
        end_date="20260729",
    )

    assert [item.rows for item in result] == [1, 1]
    assert (tmp_path / "index_weight/index_weight_000300_SH.csv").exists()
    assert (tmp_path / "index_weight_daily/index_weight_daily_000300_SH.csv").exists()


def test_stock_st_fails_closed_when_mdp_lacks_requested_date(monkeypatch, tmp_path) -> None:
    mdp = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20260728"}])
    monkeypatch.setattr(
        stock_st,
        "load_mdp_asset",
        lambda _dataset: (mdp, tmp_path / "stock_st.parquet"),
    )
    pro = SimpleNamespace(
        stock_st=lambda **_kwargs: pytest.fail("direct TuShare fallback must not run")
    )

    with pytest.raises(ReferenceAssetUnavailable, match="no rows"):
        stock_st.fetch_stock_st(
            pro,
            "20260729",
            data_dir=tmp_path,
            runner=ImmediateRunner(),
        )


def test_stock_company_fails_closed_when_mdp_lacks_requested_exchange(
    monkeypatch, tmp_path
) -> None:
    mdp = pd.DataFrame([{"ts_code": "000001.SZ", "exchange": "SZSE"}])
    monkeypatch.setattr(
        listed_company,
        "load_mdp_asset",
        lambda _dataset: (mdp, tmp_path / "stock_company.parquet"),
    )
    pro = SimpleNamespace(
        stock_company=lambda **_kwargs: pytest.fail("direct TuShare fallback must not run")
    )
    fetcher = ListedCompanyFetcher(
        pro,
        ImmediateRunner(),
        DataStore(base_dir=tmp_path / "store"),
    )

    with pytest.raises(ReferenceAssetUnavailable, match="no rows"):
        fetcher.fetch_stock_company(["SSE"])


@pytest.mark.parametrize("dataset", ["stk_managers", "share_float"])
def test_event_datasets_consume_mdp_asset(monkeypatch, tmp_path, dataset) -> None:
    frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "ann_date": "20240102", "name": "inside"},
            {"ts_code": "000002.SZ", "ann_date": "20231229", "name": "outside"},
        ]
    )
    monkeypatch.setattr(
        listed_company,
        "load_mdp_asset",
        lambda requested: (frame, tmp_path / f"{requested}.parquet"),
    )
    fetcher = ListedCompanyFetcher(
        SimpleNamespace(),
        ImmediateRunner(),
        DataStore(base_dir=tmp_path / "store"),
    )

    if dataset == "stk_managers":
        result = fetcher.fetch_stk_managers(
            date(2024, 1, 1),
            date(2024, 1, 31),
            window="month",
            resume=False,
            force=False,
        )
    else:
        result = fetcher.fetch_share_float(
            date(2024, 1, 1),
            date(2024, 1, 31),
            window="month",
            resume=False,
            force=False,
        )

    assert result.rows == 1
    curated = pd.read_csv(tmp_path / f"store/curated/{dataset}.csv")
    assert curated["name"].tolist() == ["inside"]
