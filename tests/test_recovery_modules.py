from __future__ import annotations

from pathlib import Path

from ops_common.recovery_state import atomic_write_json, read_state


def test_recovery_state_round_trips_date_scoped_receipts(tmp_path: Path) -> None:
    receipt = tmp_path / "state.json"
    atomic_write_json(receipt, {"date": "20260916", "success": True})

    assert read_state(receipt, "20260916") == {
        "date": "20260916",
        "success": True,
    }
    assert read_state(receipt, "20260915") == {}
