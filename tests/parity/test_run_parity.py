from __future__ import annotations

import json
from pathlib import Path

from parity.run_parity import main


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parity_cli_writes_clean_manifest_for_ignored_runtime_fields(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    output_root = tmp_path / "runs"
    _write(old_root / "selection_receipt.json", {"trade_date": "20260908", "generated_at": "a"})
    _write(new_root / "selection_receipt.json", {"trade_date": "20260908", "generated_at": "b"})

    status = main(
        [
            "--source-date",
            "20260908",
            "--signal-date",
            "20260909",
            "--old-root",
            str(old_root),
            "--new-root",
            str(new_root),
            "--output-root",
            str(output_root),
        ]
    )

    assert status == 0
    manifest = json.loads((output_root / "parity_20260908_20260909.json").read_text())
    assert manifest["unexplained_differences"] is False
    assert manifest["mandatory_artifacts"] == ["selection_receipt.json"]


def test_parity_cli_returns_nonzero_for_changed_mandatory_field(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    output_root = tmp_path / "runs"
    _write(old_root / "selection_receipt.json", {"trade_date": "20260908", "status": "published"})
    _write(new_root / "selection_receipt.json", {"trade_date": "20260909", "status": "published"})

    status = main(
        [
            "--source-date",
            "20260908",
            "--signal-date",
            "20260909",
            "--old-root",
            str(old_root),
            "--new-root",
            str(new_root),
            "--output-root",
            str(output_root),
        ]
    )

    assert status == 1
    manifest = json.loads((output_root / "parity_20260908_20260909.json").read_text())
    assert "trade_date" in manifest["differences"]["selection_receipt.json"][0]


def test_parity_cli_normalizes_paths_under_paths_mapping(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    output_root = tmp_path / "runs"
    _write(old_root / "morning_manifest.json", {"charts": {"paths": {"dashboard": "/old/a.png"}}})
    _write(new_root / "morning_manifest.json", {"charts": {"paths": {"dashboard": "/new/a.png"}}})

    status = main(
        [
            "--source-date",
            "20260908",
            "--signal-date",
            "20260909",
            "--old-root",
            str(old_root),
            "--new-root",
            str(new_root),
            "--output-root",
            str(output_root),
        ]
    )

    assert status == 0
