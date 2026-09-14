from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from a_share_daily import cli


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _official_cashflow(tmp_path: Path) -> tuple[Path, Path]:
    cashflow = _write(
        tmp_path / "cashflow.json",
        {
            "schema_version": "strategy_app.cashflow.official_top6.v1",
            "status": "passed",
            "research_only": True,
            "eligible_for_live": False,
            "strategy_id": "cni_980092_official_top6_v1",
            "index_code": "980092.SZ",
            "report_date": "20260914",
            "official_snapshot_date": "20260831",
            "selected_count": 6,
            "targets": [
                {
                    "symbol": f"CF{i:03d}.SZ",
                    "name": f"CF{i}",
                    "official_rank": i,
                    "official_weight": 1 / (i + 10),
                }
                for i in range(1, 7)
            ],
        },
    )
    receipt = _write(
        tmp_path / "cashflow-receipt.json",
        {
            "schema_version": "strategy_app.cashflow.official_top6.v1",
            "status": "passed",
            "research_only": True,
            "eligible_for_live": False,
            "strategy_id": "cni_980092_official_top6_v1",
            "index_code": "980092.SZ",
            "report_date": "20260914",
            "official_snapshot_date": "20260831",
            "selected_count": 6,
            "selection_sha256": hashlib.sha256(cashflow.read_bytes()).hexdigest(),
            "gates": {"snapshot_complete": "passed", "top6_listed": "passed"},
        },
    )
    return cashflow, receipt


def test_weekly_basket_dry_run_writes_report_and_does_not_send(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    cashflow, cashflow_receipt = _official_cashflow(tmp_path)
    microcap = _write(
        tmp_path / "microcap.json",
        {
            "schema_version": "microcap.selection.v1",
            "status": "passed",
            "shadow": True,
            "research_only": True,
            "eligible_for_live": False,
            "source_date": "20260911",
            "signal_date": "20260912",
            "positions": [
                {"symbol": f"MC{i:03d}.SZ", "name": f"MC{i}", "rank": i} for i in range(1, 5)
            ],
        },
    )
    output_root = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "a-share-daily",
            "weekly-basket",
            "--as-of-date",
            "20260914",
            "--cashflow",
            str(cashflow),
            "--cashflow-receipt",
            str(cashflow_receipt),
            "--microcap",
            str(microcap),
            "--output-root",
            str(output_root),
            "--dry-run",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    assert (output_root / "20260914" / "basket.json").exists()
    assert (output_root / "20260914" / "report.md").exists()
    assert (
        json.loads((output_root / "20260914" / "receipt.json").read_text())["send_status"]
        == "dry_run"
    )
    basket = json.loads((output_root / "20260914" / "basket.json").read_text())
    assert basket["config"]["quotas"] == {
        "dailywatch_family": 0,
        "cashflow": 6,
        "microcap": 4,
    }
    assert "monitoring" not in basket
    assert all(row["sleeve"] != "dailywatch_family" for row in basket["source_inputs"])
    output = json.loads(capsys.readouterr().out)
    assert output["send_status"] == "dry_run"
