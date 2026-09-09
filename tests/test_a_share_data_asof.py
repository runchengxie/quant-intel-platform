from __future__ import annotations

from pathlib import Path

from a_share_daily import data


def _partition(root: Path, dataset: str, date: str) -> None:
    path = root / dataset / "a_share_all_latest" / "data" / f"trade_date={date}"
    path.mkdir(parents=True)
    (path / "part.parquet").touch()


def test_latest_date_can_be_bounded_by_report_date(monkeypatch, tmp_path: Path) -> None:
    for date in ("20260904", "20260908"):
        _partition(tmp_path, "daily", date)
    monkeypatch.setattr(data, "_data_root", lambda: tmp_path)

    assert data._latest_date("daily") == "20260908"
    assert data._latest_date("daily", as_of_date="20260904") == "20260904"


def test_latest_date_returns_none_when_no_partition_is_at_or_before_report_date(
    monkeypatch, tmp_path: Path
) -> None:
    _partition(tmp_path, "daily", "20260908")
    monkeypatch.setattr(data, "_data_root", lambda: tmp_path)

    assert data._latest_date("daily", as_of_date="20260904") is None
