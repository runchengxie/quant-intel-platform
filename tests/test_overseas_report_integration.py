import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from a_share_daily.morning_report import render_morning_report


def test_report_rejects_unpinned_research_and_keeps_observations(tmp_path):
    path = tmp_path / "research.json"
    path.write_text("{}")
    report = render_morning_report(
        {"date": "20261029", "overseas_theme_evidence": {"path": path}},
        generated_at=datetime(2026, 10, 29, 8, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    assert "invalid_pin" in report
    assert "observations" in report


def test_report_displays_missing_research_explicitly():
    report = render_morning_report({"date": "20261029"})
    assert "Research evidence unavailable" in report
    assert "not_supplied" in report


def test_cli_accepts_evidence_pin_and_never_sends_by_default(tmp_path, monkeypatch, capsys):
    from a_share_daily import cli

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"date": "20261029"}))
    output = tmp_path / "report.md"
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    monkeypatch.setattr(
        "sys.argv",
        [
            "a-share-daily",
            "morning-report",
            "--manifest",
            str(manifest),
            "--news",
            str(tmp_path / "absent.json"),
            "--out",
            str(output),
            "--overseas-theme-evidence",
            str(bad),
            "--overseas-theme-sha256",
            hashlib.sha256(bad.read_bytes()).hexdigest(),
        ],
    )
    cli.main()
    assert "schema_invalid" in output.read_text()
    assert "schema_invalid" in capsys.readouterr().out
