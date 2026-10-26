from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
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
                    "symbol": f"600{i:03d}.SH",
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


def _weekly_args(tmp_path: Path, *, mode: str) -> list[str]:
    cashflow, cashflow_receipt = _official_cashflow(tmp_path)
    microcap = _write(
        tmp_path / "microcap.json",
        {
            "schema_version": "microcap.selection.v2",
            "status": "passed",
            "shadow": True,
            "research_only": True,
            "eligible_for_live": False,
            "signal_date": "20260911",
            "valid_from": "20260911",
            "valid_until": "20260917",
            "positions": [
                {"symbol": f"000{i:03d}.SZ", "name": f"MC{i}", "rank": i} for i in range(1, 11)
            ],
        },
    )
    microcap_receipt = _write(
        tmp_path / "microcap-receipt.json",
        {
            "schema_version": "microcap.selection.receipt.v2",
            "status": "passed",
            "signal_date": "20260911",
            "valid_from": "20260911",
            "valid_until": "20260917",
            "research_only": True,
            "eligible_for_live": False,
            "artifact_sha256": hashlib.sha256(microcap.read_bytes()).hexdigest(),
        },
    )
    instruments = tmp_path / "instruments.parquet"
    market = tmp_path / "market.parquet"
    calendar = tmp_path / "calendar.parquet"
    symbols = [f"600{i:03d}.SH" for i in range(1, 7)] + [f"000{i:03d}.SZ" for i in range(1, 5)]
    pd.DataFrame(
        {
            "ts_code": symbols,
            "name": symbols,
            "list_status": "L",
            "list_date": "20100101",
            "delist_date": None,
        }
    ).to_parquet(instruments)
    pd.DataFrame(
        {
            "ts_code": symbols,
            "trade_date": "20260911",
            "amount": 30_000_000.0,
            "is_st": False,
            "is_suspended": False,
            "close": 10.0,
        }
    ).to_parquet(market)
    pd.DataFrame({"cal_date": ["20260911", "20260914"], "is_open": [1, 1]}).to_parquet(calendar)
    return [
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
        "--microcap-receipt",
        str(microcap_receipt),
        "--instruments",
        str(instruments),
        "--market-snapshot",
        str(market),
        "--calendar",
        str(calendar),
        "--output-root",
        str(tmp_path / "output"),
        "--state-root",
        str(tmp_path / "state"),
        "--personal-chat-id",
        "ou_owner",
        mode,
    ]


def test_weekly_basket_parser_has_no_legacy_strategy_arguments() -> None:
    parser = cli._build_parser()
    weekly = next(
        action.choices["weekly-basket"]
        for action in parser._actions
        if getattr(action, "choices", None) and "weekly-basket" in action.choices
    )
    options = {option for action in weekly._actions for option in action.option_strings}
    assert "--dailywatch" not in options
    assert "--d11-h5" not in options
    assert "--microcap-quota" not in options
    assert "--group-chat-id" in options


def test_weekly_basket_dry_run_writes_report_and_does_not_send(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_root = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", _weekly_args(tmp_path, mode="--dry-run"))

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


def test_weekly_basket_send_requires_performance_before_delivery(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    called = False

    def forbidden_delivery(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("delivery must not run")

    monkeypatch.setattr(sys, "argv", _weekly_args(tmp_path, mode="--send"))
    monkeypatch.setattr(
        "a_share_daily.weekly_client_basket_delivery.send_personal_basket_report",
        forbidden_delivery,
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    assert called is False
    assert "--performance is required" in capsys.readouterr().err
    assert not (tmp_path / "output" / "20260914" / "report.png").exists()


def test_weekly_basket_send_rejects_invalid_performance_before_delivery(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    performance = _write(tmp_path / "performance.json", {"schema_version": "wrong.v1"})
    argv = _weekly_args(tmp_path, mode="--send")
    argv[2:2] = ["--performance", str(performance)]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    assert "unsupported performance artifact schema" in capsys.readouterr().err
    assert not (tmp_path / "output" / "20260914" / "report.png").exists()


@pytest.mark.parametrize("personal_only", [False, True])
def test_weekly_basket_personal_only_excludes_configured_group(
    tmp_path: Path, monkeypatch, personal_only: bool
) -> None:
    from types import SimpleNamespace

    from a_share_daily.weekly_basket_command import _deliver_weekly_basket

    args = SimpleNamespace(
        send=True,
        personal_only=personal_only,
        output_root=tmp_path,
        as_of_date="20260914",
        personal_chat_id="ou_owner",
        group_chat_id="oc_group",
        lark_cli="unused",
    )
    receipt = _write(tmp_path / "receipt.json", {})
    sent = []

    def send_report(*args, **kwargs):
        sent.append(kwargs)
        return SimpleNamespace(status="sent", image_status="sent")

    monkeypatch.setattr(
        "a_share_daily.weekly_client_basket_delivery.send_basket_report", send_report
    )
    _, okay = _deliver_weekly_basket(args, {"receipt": receipt}, {}, "report")
    assert okay
    assert [row["target_kind"] for row in sent] == (
        ["personal"] if personal_only else ["personal", "group"]
    )
    assert sent[0]["receipt_path"] == tmp_path / "20260914/delivery/personal.json"
    assert sent[0]["target_id"] == "ou_owner"


def test_weekly_basket_parser_accepts_personal_only_without_group(tmp_path: Path) -> None:
    args = cli._build_parser().parse_args(
        _weekly_args(tmp_path, mode="--send")[1:] + ["--personal-only"]
    )
    assert args.personal_only


@pytest.mark.parametrize("personal_only", [False, True])
def test_weekly_basket_missing_group_requires_explicit_personal_only(
    tmp_path: Path, monkeypatch, capsys, personal_only: bool
) -> None:
    from types import SimpleNamespace

    from a_share_daily import weekly_basket_command

    args = cli._build_parser().parse_args(_weekly_args(tmp_path, mode="--send")[1:])
    args.performance = "performance.json"
    args.group_chat_id = None
    args.personal_only = personal_only
    monkeypatch.setattr(
        "a_share_daily.reporting.performance.load_performance",
        lambda *args, **kwargs: SimpleNamespace(to_payload=lambda: {}),
    )

    def admitted(args):
        raise RuntimeError("admitted without group")

    monkeypatch.setattr(weekly_basket_command, "_prepare_weekly_basket", admitted)
    if personal_only:
        with pytest.raises(RuntimeError, match="admitted without group"):
            weekly_basket_command._cmd_weekly_basket(args)
    else:
        assert weekly_basket_command._cmd_weekly_basket(args) == 1
        assert "--group-chat-id is required" in capsys.readouterr().err
