from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from a_share_daily import minute_owner_validation as owner_validation
from a_share_daily.daily_watch20_raw_completeness import publish_daily_watch_receipt
from a_share_daily.minute_owner_validation import validate_exchange_overlay


def _receipt(root: Path) -> dict:
    return {
        "validation_schema_version": "marketdata.minute_exchange_overlay.v1",
        "exchange": "SZ",
        "schema_version": "tushare.a_share.minute_partition.promotion.v1",
        "trade_date": "20260706",
        "partition_path": str(root / "trade_date=20260706/part-00000.parquet"),
        "sidecar_path": str(root / "trade_date=20260706/_minute_mirror.json"),
        "partition_sha256": "a" * 64,
        "sidecar_sha256": "b" * 64,
        "rows": 241,
        "symbols": 1,
        "market_symbol_counts": {"SH": 0, "SZ": 1, "BJ": 0},
        "expected_bars_per_symbol": 241,
        "universe_hash": "c" * 64,
        "universe_rule": "owner_rule:exchange=SZ",
        "universe_source": "synthetic",
        "mirror_generated_at": "2026-07-06T08:00:00Z",
    }


def _cli(tmp_path: Path, receipt: dict, *, exit_code: int = 0, malformed: bool = False) -> Path:
    script = tmp_path / "marketdata"
    script.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
        f"Path({str(tmp_path / 'invocation.json')!r}).write_text(json.dumps("
        "{'argv':sys.argv[1:],'cwd':os.getcwd(),'pythonpath':os.environ.get('PYTHONPATH'),"
        "'pythonhome':os.environ.get('PYTHONHOME')}))\n"
        + ("print('not json')\n" if malformed else f"print(json.dumps({receipt!r}))\n")
        + f"sys.exit({exit_code})\n"
    )
    script.chmod(0o755)
    return script


def test_installed_owner_cli_returns_original_receipt_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "overlay"
    payload = _receipt(root)
    cli = _cli(tmp_path, payload)
    monkeypatch.setenv("PYTHONPATH", "/untrusted/source")
    monkeypatch.setenv("PYTHONHOME", "/untrusted/python")
    receipt = validate_exchange_overlay(root, trade_date="20260706", exchange="SZ", cli=cli)
    assert receipt == {
        k: v for k, v in payload.items() if k not in {"exchange", "validation_schema_version"}
    }
    invocation = json.loads((tmp_path / "invocation.json").read_text())
    assert invocation["argv"] == [
        "tushare",
        "validate-minute-partition",
        "--data-root",
        str(root.resolve()),
        "--trade-date",
        "20260706",
        "--exchange",
        "SZ",
    ]
    assert invocation["pythonpath"] is None
    assert invocation["pythonhome"] is None
    assert invocation["cwd"] != str(Path.cwd())
    assert not Path(invocation["cwd"]).exists()


def test_relative_owner_configuration_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cli(tmp_path, _receipt(tmp_path / "overlay"))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="absolute"):
        validate_exchange_overlay(
            tmp_path / "overlay", trade_date="20260706", exchange="SZ", cli=Path("marketdata")
        )


@pytest.mark.parametrize(
    "error", [OSError("launch failed"), subprocess.TimeoutExpired("marketdata", 180)]
)
def test_owner_launch_failure_and_timeout_are_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    cli = _cli(tmp_path, _receipt(tmp_path / "overlay"))

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(owner_validation.subprocess, "run", fail)
    with pytest.raises(ValueError, match="owner"):
        validate_exchange_overlay(
            tmp_path / "overlay", trade_date="20260706", exchange="SZ", cli=cli
        )


def test_missing_owner_cli_never_uses_python_import_fallback(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="owner"):
        validate_exchange_overlay(
            tmp_path, trade_date="20260706", exchange="SZ", cli=tmp_path / "missing"
        )


@pytest.mark.parametrize(
    "corruption",
    ["schema", "date", "exchange", "counts", "missing", "hash", "rows", "path", "json", "exit"],
)
def test_bad_owner_responses_fail_closed(tmp_path: Path, corruption: str) -> None:
    root = tmp_path / "overlay"
    receipt = _receipt(root)
    changes = {
        "schema": ("validation_schema_version", "unknown.v2"),
        "date": ("trade_date", "20260707"),
        "exchange": ("exchange", "SH"),
        "counts": ("market_symbol_counts", {"SH": 1, "SZ": 1, "BJ": 0}),
        "hash": ("partition_sha256", "not-a-hash"),
        "rows": ("rows", 0),
        "path": ("partition_path", str(tmp_path / "unrelated.parquet")),
    }
    if corruption in changes:
        key, value = changes[corruption]
        receipt[key] = value
    elif corruption == "missing":
        del receipt["universe_hash"]
    cli = _cli(
        tmp_path,
        receipt,
        exit_code=3 if corruption == "exit" else 0,
        malformed=corruption == "json",
    )
    with pytest.raises(ValueError, match="owner"):
        validate_exchange_overlay(root, trade_date="20260706", exchange="SZ", cli=cli)


def test_failed_owner_never_writes_a_completion_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    freshness = tmp_path / "freshness.json"
    freshness.write_text(
        json.dumps(
            {
                "required_minute_date": "20260706",
                "status": "ready",
                "minute_source": "tushare_sh_sz_overlay",
            }
        )
    )
    cli = _cli(tmp_path, {}, exit_code=1)
    monkeypatch.setenv("MARKETDATA_CLI", str(cli))
    markers = tmp_path / "markers"
    with pytest.raises(ValueError, match="owner"):
        publish_daily_watch_receipt(
            freshness_path=freshness,
            trade_date="20260706",
            marker_root=markers,
            overlay_roots={"SH": tmp_path / "sh", "SZ": tmp_path / "sz"},
        )
    assert not markers.exists()
