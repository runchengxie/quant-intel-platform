from __future__ import annotations

from pathlib import Path

from a_share_daily.weekly_context import validate_weekly_context, write_weekly_context


def test_weekly_context_sidecar_binds_cutoff_and_report(tmp_path: Path) -> None:
    report_path = tmp_path / "weekly_recap.md"
    metadata_path = tmp_path / "weekly_recap.meta.json"

    write_weekly_context(
        report_path,
        metadata_path,
        "## 本周复盘\n\n正文",
        target_trade_date="20260821",
        actual_through="20260821",
    )

    assert validate_weekly_context(report_path, metadata_path, "20260821") == (
        True,
        "weekly context is current",
    )
    assert "<!--" not in report_path.read_text(encoding="utf-8")


def test_weekly_context_rejects_stale_or_modified_report(tmp_path: Path) -> None:
    report_path = tmp_path / "weekly_recap.md"
    metadata_path = tmp_path / "weekly_recap.meta.json"
    write_weekly_context(
        report_path,
        metadata_path,
        "原始正文",
        target_trade_date="20260821",
        actual_through="20260820",
    )

    valid, reason = validate_weekly_context(report_path, metadata_path, "20260821")
    assert valid is False
    assert reason == "weekly context actual cutoff mismatch"

    write_weekly_context(
        report_path,
        metadata_path,
        "原始正文",
        target_trade_date="20260821",
        actual_through="20260821",
    )
    report_path.write_text("被修改的正文", encoding="utf-8")
    valid, reason = validate_weekly_context(report_path, metadata_path, "20260821")
    assert valid is False
    assert reason == "weekly context report hash mismatch"
