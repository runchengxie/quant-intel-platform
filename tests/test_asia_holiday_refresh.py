"""Holiday publication consumes dated Asia facts without calling A-share review."""

import json
import sys

import pandas as pd
import pytest

from a_share_daily.public_report_refresh import RefreshRequest, refresh_reports


def inputs(tmp_path):
    data = tmp_path / "data"
    calendar = data / "assets/tushare/a_share/trade_cal/a_share_trade_cal_latest.parquet"
    calendar.parent.mkdir(parents=True)
    pd.DataFrame({"exchange": ["SSE"], "cal_date": ["20261005"], "is_open": [0]}).to_parquet(
        calendar
    )
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    owner = tmp_path / "owner"
    owner.write_text(f"#!{sys.executable}\nraise SystemExit(99)\n")
    owner.chmod(0o700)
    return data, calendar, snapshots, owner


def test_holiday_refresh_uses_validated_dated_asia_receipt(tmp_path):
    data, _calendar, snapshots, owner = inputs(tmp_path)
    payload = holiday_payload()
    receipt = data / "reports/market-intel/asia_evening/20261005.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps(payload))
    output = tmp_path / "out"
    manifest = refresh_reports(RefreshRequest(owner, data, snapshots, output, "2026-10-05"))
    entry = json.loads(manifest.read_text())["reports"][0]
    text = (output / entry["path"]).read_text()
    assert entry["date"] == "2026-10-05"
    assert "25,000" in text or "25000" in text
    assert "休市" in text
    assert "上涨 3000" not in text


def test_holiday_receipt_with_stale_open_quote_is_rejected(tmp_path):
    data, _calendar, snapshots, owner = inputs(tmp_path)
    payload = holiday_payload()
    payload["markets"]["HK"]["observation_date"] = "2026-10-02"
    receipt = data / "reports/market-intel/asia_evening/20261005.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="stale"):
        refresh_reports(RefreshRequest(owner, data, snapshots, tmp_path / "out", "2026-10-05"))


def holiday_payload():
    return {
        "schema_version": "market_intel.asia_evening.v2",
        "date": "20261005",
        "generated_at": "2026-10-05T10:00:00+00:00",
        "markets": {
            "CN": {"status": "closed", "observation_date": None},
            "KR": {"status": "closed", "observation_date": None},
            "JP": {"status": "missing", "observation_date": None},
            "HK": {
                "status": "open",
                "observation_date": "2026-10-05",
                "close": 25000.0,
                "change_pct": 0.0,
                "previous_session": "2026-10-02",
                "previous_close": 25000.0,
                "retrieved_at": "2026-10-05T09:00:00+00:00",
                "source_url": "https://finance.yahoo.com/quote/^HSI/history/",
                "source_time": "2026-10-05T08:00:00+00:00",
                "evidence_id": "asia.close." + "a" * 64,
            },
        },
    }


def test_missing_session_calendar_cannot_fall_back_to_a_share_review(tmp_path):
    data, calendar, snapshots, owner = inputs(tmp_path)
    calendar.unlink()
    with pytest.raises(ValueError, match="calendar"):
        refresh_reports(RefreshRequest(owner, data, snapshots, tmp_path / "out", "2026-10-05"))


def test_legacy_receipt_cannot_claim_close_before_generation(tmp_path):
    data, _calendar, snapshots, owner = inputs(tmp_path)
    payload = holiday_payload()
    payload["schema_version"] = "market_intel.asia_evening.v1"
    payload["markets"]["HK"].pop("retrieved_at")
    payload["generated_at"] = "2026-10-05T07:00:00+00:00"
    receipt = data / "reports/market-intel/asia_evening/20261005.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="legacy.*provenance"):
        refresh_reports(RefreshRequest(owner, data, snapshots, tmp_path / "out", "2026-10-05"))


def test_installed_refresh_ignores_empty_ancestor_git_marker(tmp_path, monkeypatch):
    from a_share_daily import public_report_refresh as refresh

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    data, _calendar, snapshots, owner = inputs(workspace)
    monkeypatch.setattr(
        refresh,
        "__file__",
        str(tmp_path / "installed/site-packages/a_share_daily/public_report_refresh.py"),
    )
    refresh.validate_paths(owner, data, snapshots, workspace / "output")


@pytest.mark.parametrize("marker_kind", ["repository", "worktree", "symlink"])
def test_installed_refresh_rejects_foreign_repository_markers(tmp_path, monkeypatch, marker_kind):
    from a_share_daily import public_report_refresh as refresh

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    marker = workspace / ".git"
    if marker_kind == "repository":
        marker.mkdir()
        (marker / "HEAD").write_text("ref: refs/heads/main\n")
    elif marker_kind == "worktree":
        marker.write_text("gitdir: /external/worktree\n")
    else:
        target = tmp_path / "empty-marker"
        target.mkdir()
        marker.symlink_to(target, target_is_directory=True)
    data, _calendar, snapshots, owner = inputs(workspace)
    monkeypatch.setattr(
        refresh,
        "__file__",
        str(tmp_path / "installed/site-packages/a_share_daily/public_report_refresh.py"),
    )
    with pytest.raises(ValueError, match="outside Git"):
        refresh.validate_paths(owner, data, snapshots, workspace / "output")
