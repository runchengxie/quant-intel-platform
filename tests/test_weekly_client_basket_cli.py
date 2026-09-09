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


def test_weekly_basket_dry_run_writes_report_and_does_not_send(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dailywatch = _write(
        tmp_path / "dailywatch.json",
        {
            "status": "passed",
            "source_date": "20260911",
            "signal_date": "20260912",
            "positions": [
                {"symbol": f"DW{i:03d}.SZ", "name": f"DW{i}", "rank": i, "score": 1 / i}
                for i in range(1, 6)
            ],
        },
    )
    cashflow = _write(
        tmp_path / "cashflow.json",
        {
            "schema_version": "strategy_app.cashflow.selection.v1",
            "status": "passed",
            "research_only": True,
            "eligible_for_live": False,
            "strategy_id": "cashflow_quality_top50_v1",
            "source_date": "20260901",
            "signal_date": "20260902",
            "targets": [
                {"symbol": f"CF{i:03d}.SZ", "name": f"CF{i}", "target_weight": 1 / 3}
                for i in range(1, 4)
            ],
        },
    )
    cashflow_receipt = _write(
        tmp_path / "cashflow-receipt.json",
        {
            "schema_version": "strategy_pipeline.cashflow.publication.v1",
            "status": "passed",
            "selection_sha256": hashlib.sha256(cashflow.read_bytes()).hexdigest(),
        },
    )
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
                {"symbol": f"MC{i:03d}.SZ", "name": f"MC{i}", "rank": i} for i in range(1, 4)
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
            "--dailywatch",
            str(dailywatch),
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
        == "not_requested"
    )
    assert "not_requested" in capsys.readouterr().out
