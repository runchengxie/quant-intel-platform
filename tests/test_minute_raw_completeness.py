from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from a_share_daily import daily_watch20_raw_completeness as MODULE

SCHEMA_VERSION = MODULE.SCHEMA_VERSION
publish_daily_watch_receipt = MODULE.publish_daily_watch_receipt
NOW = datetime(2026, 7, 20, 13, 5, tzinfo=UTC)


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_daily_watch_receipt_accepts_candidate_failure_after_exact_minute_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    freshness_path = tmp_path / "freshness.json"
    freshness_path.write_text(
        json.dumps(
            {
                "status": "ready",
                "source_date": "20260720",
                "signal_date": "20260721",
                "required_minute_date": "20260720",
                "minute_source": "tushare_sh_sz_overlay",
            }
        ),
        encoding="utf-8",
    )
    validations: list[tuple[Path, str, str]] = []

    def validate_overlay(root: Path, *, trade_date: str, exchange: str) -> dict[str, object]:
        validations.append((root, trade_date, exchange))
        return {
            "trade_date": trade_date,
            "partition_sha256": exchange.lower() * 32,
            "market_symbol_counts": {exchange: 1},
        }

    monkeypatch.setattr(MODULE, "_validate_exchange_overlay", validate_overlay)
    overlay_roots = {"SH": tmp_path / "sh", "SZ": tmp_path / "sz"}

    marker = publish_daily_watch_receipt(
        freshness_path=freshness_path,
        trade_date="20260720",
        marker_root=tmp_path / "markers",
        overlay_roots=overlay_roots,
        now=NOW,
    )

    receipt = _read(marker)
    assert marker.name == "daily_watch20.json"
    assert receipt["schema_version"] == SCHEMA_VERSION
    assert receipt["quota_date"] == "20260720"
    assert receipt["evidence"]["minute_source"] == "tushare_sh_sz_overlay"
    assert set(receipt["evidence"]["partition_receipts"]) == {"SH", "SZ"}
    assert Path(receipt["evidence_path"]).is_file()
    assert receipt["evidence_path"] != str(freshness_path)
    assert validations == [
        (overlay_roots["SH"], "20260720", "SH"),
        (overlay_roots["SZ"], "20260720", "SZ"),
    ]

    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["status"] = "unavailable"
    freshness["reasons"] = ["candidate pool unavailable: rank gap"]
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")
    publish_daily_watch_receipt(
        freshness_path=freshness_path,
        trade_date="20260720",
        marker_root=tmp_path / "markers",
        overlay_roots=overlay_roots,
        now=NOW,
    )


def test_daily_watch_receipt_rejects_wrong_date_or_missing_minute_source(tmp_path: Path) -> None:
    freshness_path = tmp_path / "freshness.json"
    payload = {
        "status": "ready",
        "source_date": "20260720",
        "signal_date": "20260721",
        "required_minute_date": "20260719",
        "minute_source": "canonical",
    }
    freshness_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="date mismatch"):
        publish_daily_watch_receipt(
            freshness_path=freshness_path,
            trade_date="20260720",
            marker_root=tmp_path / "markers",
            now=NOW,
        )

    payload["required_minute_date"] = "20260720"
    payload["minute_source"] = None
    freshness_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="no complete minute source"):
        publish_daily_watch_receipt(
            freshness_path=freshness_path,
            trade_date="20260720",
            marker_root=tmp_path / "markers",
            now=NOW,
        )
