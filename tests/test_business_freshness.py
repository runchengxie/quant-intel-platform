from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ops_common.business_freshness import (
    CORE_PARTITIONS,
    FreshnessContext,
    build_business_targets,
    missing_daily_sessions,
    probe_stage,
    report_audit_path,
)
from ops_common.report_window import delivery_decision

SHANGHAI = ZoneInfo("Asia/Shanghai")
OPEN_DATES = ("20260806", "20260807", "20260810", "20260811")


def test_business_targets_follow_stage_data_availability_cutoffs() -> None:
    before_open = build_business_targets(datetime(2026, 8, 11, 3, 0, tzinfo=SHANGHAI), OPEN_DATES)
    after_close = build_business_targets(datetime(2026, 8, 11, 18, 0, tzinfo=SHANGHAI), OPEN_DATES)

    assert before_open.eod_date == "20260810"
    assert after_close.eod_date == "20260811"
    assert after_close.minute_date == "20260810"
    assert after_close.report_data_date == "20260810"


def test_missing_daily_sessions_lists_every_open_tail_gap(tmp_path: Path) -> None:
    context = FreshnessContext(tmp_path / "project", tmp_path / "data", OPEN_DATES)
    asset_root = context.data_root / "assets/tushare/a_share"
    for relative in CORE_PARTITIONS:
        partition = asset_root / relative / "data/trade_date=20260807"
        partition.mkdir(parents=True)

    assert missing_daily_sessions(context, "20260811") == ("20260810", "20260811")


def test_daily_probe_requires_all_core_target_partitions(tmp_path: Path) -> None:
    context = FreshnessContext(tmp_path / "project", tmp_path / "data", OPEN_DATES)
    asset_root = context.data_root / "assets/tushare/a_share"
    for relative in CORE_PARTITIONS:
        partition = asset_root / relative / "data/trade_date=20260810"
        partition.mkdir(parents=True)
        (partition / "part.parquet").write_bytes(b"parquet")

    result = probe_stage(
        context,
        stage_key="daily_market",
        target_date="20260810",
        signal_date="20260811",
    )

    assert result.fresh is True
    missing = asset_root / CORE_PARTITIONS[-1] / "data/trade_date=20260810/part.parquet"
    missing.unlink()
    assert (
        probe_stage(
            context,
            stage_key="daily_market",
            target_date="20260810",
            signal_date="20260811",
        ).fresh
        is False
    )


def test_report_dataset_probe_treats_optional_enhancements_as_non_blocking(
    tmp_path: Path,
) -> None:
    context = FreshnessContext(tmp_path / "release", tmp_path / "data", OPEN_DATES)
    reports = context.data_root / "reports"
    reports.mkdir(parents=True)
    (reports / "a_share_report_dataset_refresh_20260810.json").write_text(
        json.dumps(
            {
                "trade_date": "20260810",
                "datasets": [
                    {"dataset": "dc_concept", "status": "ready"},
                    {"dataset": "kpl_concept_cons", "status": "ready"},
                    {"dataset": "limit_list_ths", "status": "ready"},
                    {"dataset": "dc_concept_cons", "status": "degraded"},
                    {"dataset": "ths_hot", "status": "missing"},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = probe_stage(
        context,
        stage_key="report_datasets",
        target_date="20260810",
        signal_date="20260811",
    )

    assert result.fresh is True


def test_report_dataset_probe_still_blocks_missing_required_dataset(tmp_path: Path) -> None:
    context = FreshnessContext(tmp_path / "release", tmp_path / "data", OPEN_DATES)
    reports = context.data_root / "reports"
    reports.mkdir(parents=True)
    (reports / "a_share_report_dataset_refresh_20260810.json").write_text(
        json.dumps(
            {
                "trade_date": "20260810",
                "datasets": [
                    {"dataset": "dc_concept", "status": "ready"},
                    {"dataset": "kpl_concept_cons", "status": "missing"},
                    {"dataset": "limit_list_ths", "status": "ready"},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = probe_stage(
        context,
        stage_key="report_datasets",
        target_date="20260810",
        signal_date="20260811",
    )

    assert result.fresh is False
    assert "kpl_concept_cons:missing" in result.evidence


def test_current_contract_probe_requires_daily_clean_sentinel_file(tmp_path: Path) -> None:
    context = FreshnessContext(tmp_path / "project", tmp_path / "data", OPEN_DATES)
    reports = context.data_root / "reports"
    reports.mkdir(parents=True)
    (reports / "a_share_current_release_20150101_20260810.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checks": {
                    "daily_clean_manifest": {
                        "status": "completed",
                        "output_dir": str(
                            context.data_root
                            / "assets/tushare/a_share/daily/a_share_all_20150101_20260810_daily_clean"
                        ),
                    }
                },
            }
        )
    )

    result = probe_stage(
        context,
        stage_key="current_contract",
        target_date="20260810",
        signal_date="20260811",
    )

    assert result.fresh is False
    assert result.status == "stale"
    assert "000001.SZ.parquet" in result.detail


def test_current_contract_probe_accepts_complete_daily_clean_output(tmp_path: Path) -> None:
    context = FreshnessContext(tmp_path / "project", tmp_path / "data", OPEN_DATES)
    output_dir = (
        context.data_root / "assets/tushare/a_share/daily/a_share_all_20150101_20260810_daily_clean"
    )
    manifest = output_dir / "manifest.yml"
    sentinel = output_dir / "data/000001.SZ.parquet"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"status: completed\nquery:\n  end_date: '20260810'\noutput_dir: {output_dir}\n",
        encoding="utf-8",
    )
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"parquet")
    reports = context.data_root / "reports"
    reports.mkdir(parents=True)
    (reports / "a_share_current_release_20150101_20260810.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checks": {
                    "daily_clean_manifest": {
                        "as_of_date": "20260810",
                        "status": "completed",
                        "manifest_path": str(manifest),
                        "output_dir": str(output_dir),
                    }
                },
            }
        )
    )

    result = probe_stage(
        context,
        stage_key="current_contract",
        target_date="20260810",
        signal_date="20260811",
    )

    assert result.fresh is True


def test_current_contract_probe_rejects_stale_daily_clean_manifest(tmp_path: Path) -> None:
    context = FreshnessContext(tmp_path / "project", tmp_path / "data", OPEN_DATES)
    output_dir = (
        context.data_root / "assets/tushare/a_share/daily/a_share_all_20150101_20260810_daily_clean"
    )
    manifest = output_dir / "manifest.yml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"status: completed\nquery:\n  end_date: '20260809'\noutput_dir: {output_dir}\n",
        encoding="utf-8",
    )
    sentinel = output_dir / "data/000001.SZ.parquet"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"parquet")
    reports = context.data_root / "reports"
    reports.mkdir(parents=True)
    (reports / "a_share_current_release_20150101_20260810.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checks": {
                    "daily_clean_manifest": {
                        "as_of_date": "20260810",
                        "status": "completed",
                        "manifest_path": str(manifest),
                        "output_dir": str(output_dir),
                    }
                },
            }
        )
    )

    result = probe_stage(
        context,
        stage_key="current_contract",
        target_date="20260810",
        signal_date="20260811",
    )

    assert result.fresh is False


def test_report_probe_uses_stable_delivery_state_dir(monkeypatch, tmp_path: Path) -> None:
    context = FreshnessContext(tmp_path / "release", tmp_path / "data", OPEN_DATES)
    delivery_dir = tmp_path / "stable-delivery-state"
    delivery_dir.mkdir()
    (delivery_dir / "evening_latest.json").write_text(
        json.dumps(
            {
                "success": True,
                "trade_date": "20260810",
                    "generated_at": "2026-08-10T11:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(delivery_dir))

    result = probe_stage(
        context,
        stage_key="evening_report",
        target_date="20260810",
        signal_date="20260810",
    )

    assert result.fresh is True
    assert result.evidence == (str(delivery_dir / "evening_latest.json"),)


def test_morning_probe_uses_stable_strategy_delivery_receipts(
    monkeypatch, tmp_path: Path
) -> None:
    context = FreshnessContext(tmp_path / "release", tmp_path / "data", OPEN_DATES)
    delivery_dir = tmp_path / "stable-delivery-state"
    output_dir = tmp_path / "stable-output" / "a_share_daily"
    delivery_dir.mkdir()
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(delivery_dir))
    monkeypatch.setenv("A_SHARE_OUTPUT_DIR", str(output_dir))
    (delivery_dir / "morning_latest.json").write_text(
        json.dumps(
            {
                "success": True,
                "trade_date": "20260810",
                "generated_at": "2026-08-11T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    for product in ("daily_watch20", "d11_h5_shadow"):
        receipt = output_dir / product / "20260811" / "delivery_receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(
            json.dumps(
                {
                    "success": True,
                    "source_date": "20260810",
                    "signal_date": "20260811",
                }
            ),
            encoding="utf-8",
        )

    result = probe_stage(
        context,
        stage_key="morning_report",
        target_date="20260810",
        signal_date="20260811",
    )

    assert result.fresh is True
    assert str(output_dir) in " ".join(result.evidence)


def test_report_audit_uses_stable_recovery_state_root(monkeypatch, tmp_path: Path) -> None:
    stable_root = tmp_path / "stable-recovery-state"
    monkeypatch.setenv("SCHEDULED_RECOVERY_STATE_ROOT", str(stable_root))

    context = FreshnessContext(tmp_path / "release", tmp_path / "data", OPEN_DATES)
    assert report_audit_path(context, "morning", "20260811") == (
        stable_root / "report_audits/morning/20260811.json"
    )


def test_report_windows_deliver_only_current_report_inside_window() -> None:
    assert (
        delivery_decision(
            "morning",
            signal_date="20260811",
            now=datetime(2026, 8, 11, 8, 0, tzinfo=SHANGHAI),
        ).mode
        == "deliver"
    )
    assert (
        delivery_decision(
            "morning",
            signal_date="20260811",
            now=datetime(2026, 8, 11, 10, 0, tzinfo=SHANGHAI),
        ).mode
        == "audit_only"
    )
    assert (
        delivery_decision(
            "evening",
            signal_date="20260810",
            now=datetime(2026, 8, 11, 3, 0, tzinfo=SHANGHAI),
        ).mode
        == "audit_only"
    )
