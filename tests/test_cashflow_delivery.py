from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from a_share_daily import cashflow_delivery as delivery


def _artifact() -> dict[str, object]:
    return {
        "schema_version": "strategy_app.cashflow.selection.v1",
        "status": "passed",
        "research_only": True,
        "eligible_for_live": False,
        "strategy_id": "cashflow_quality_top50_v1",
        "policy_id": "cashflow_quality_top50_v1.quarterly_fcf_cap10.v1",
        "policy": {
            "strategy_id": "cashflow_quality_top50_v1",
            "policy_id": "cashflow_quality_top50_v1.quarterly_fcf_cap10.v1",
            "top_n": 50,
            "max_weight": 0.10,
            "rebalance_frequency": "quarterly",
            "signal_timing": "source_close_to_next_open",
        },
        "source_date": "20260904",
        "signal_date": "20260907",
        "content_sha256": "a" * 64,
        "targets": [
            {
                "symbol": "000001.SZ",
                "name": "ç²",
                "selection_rank": 1,
                "target_weight": 0.6,
                "delta_weight": 0.6,
                "is_new": True,
            },
            {
                "symbol": "000002.SZ",
                "name": "ä¹",
                "selection_rank": 2,
                "target_weight": 0.4,
                "delta_weight": 0.4,
                "is_new": True,
            },
        ],
    }


def _publication_receipt(artifact: dict[str, object], selection_path: Path) -> Path:
    receipt_path = selection_path.with_name("publication-receipt.json")
    selection_sha256 = delivery._sha256_file(selection_path)
    identity = {
        "strategy_id": artifact["strategy_id"],
        "policy_id": artifact["policy_id"],
        "source_date": artifact["source_date"],
        "signal_date": artifact["signal_date"],
        "selection_sha256": selection_sha256,
        "readiness_sha256": "b" * 64,
    }
    publication_sha256 = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": delivery.PUBLICATION_SCHEMA,
                "publication_tier": "feishu_shadow",
                "status": "passed",
                "research_only": True,
                "eligible_for_live": False,
                "strategy_id": artifact["strategy_id"],
                "policy_id": artifact["policy_id"],
                "source_date": artifact["source_date"],
                "signal_date": artifact["signal_date"],
                "selection_sha256": selection_sha256,
                "readiness_sha256": "b" * 64,
                "publication_sha256": publication_sha256,
            }
        ),
        encoding="utf-8",
    )
    return receipt_path


def test_validate_publication_receipt_rejects_identity_hash_drift(tmp_path: Path) -> None:
    artifact = _artifact()
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(artifact), encoding="utf-8")
    publication_path = _publication_receipt(artifact, selection_path)
    payload = json.loads(publication_path.read_text(encoding="utf-8"))
    payload["readiness_sha256"] = "c" * 64
    publication_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(delivery.CashflowDeliveryError, match="publication_sha256"):
        delivery.validate_publication_receipt(
            publication_path, selection_path=selection_path, artifact=artifact
        )


def test_load_selection_rejects_live_eligible_artifact(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["eligible_for_live"] = True
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(delivery.CashflowDeliveryError, match="eligible_for_live"):
        delivery.load_selection(path, expected_source_date="20260904", expected_signal_date="20260907")


def test_load_selection_rejects_unknown_policy(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["policy_id"] = "cashflow_quality_top50_v1.weekly_uncapped.v0"
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(delivery.CashflowDeliveryError, match="policy"):
        delivery.load_selection(path, expected_source_date="20260904", expected_signal_date="20260907")


def test_render_markdown_contains_identity_and_target_weights() -> None:
    markdown = delivery.render_markdown(_artifact())

    assert "ç°éæµè´¨é Top50" in markdown
    assert "2026-09-04" in markdown
    assert "000001" in markdown
    assert "60.0%" in markdown
    assert "ç ç©¶å½±å­" in markdown


def test_load_executable_artifact_validates_lot_rounded_targets(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact.update(
        {
            "schema_version": "strategy_app.cashflow.executable.v1",
            "policy": {
                "portfolio_value": 500_000.0,
                "cash_reserve": 0.03,
                "max_holdings": 25,
            },
            "price_date": "20260904",
            "invested_amount": 470_000.0,
            "cash_amount": 30_000.0,
        }
    )
    artifact["targets"] = [
        {**row, "shares": shares, "actual_amount": amount, "actual_weight": amount / 500_000}
        for row, shares, amount in zip(
            artifact["targets"], [12_500, 3_700], [250_000.0, 220_000.0], strict=True
        )
    ]
    path = tmp_path / "executable.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    loaded = delivery.load_executable(
        path, expected_source_date="20260904", expected_signal_date="20260907"
    )

    assert loaded["schema_version"] == "strategy_app.cashflow.executable.v1"
    assert "å®éè¡æ°" in delivery.render_markdown(loaded)


def test_load_executable_artifact_rejects_non_lot_shares(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact.update(
        {
            "schema_version": "strategy_app.cashflow.executable.v1",
            "policy": {"portfolio_value": 500_000.0},
        }
    )
    artifact["targets"][0]["shares"] = 101
    path = tmp_path / "executable.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(delivery.CashflowDeliveryError, match="lot"):
        delivery.load_executable(path, expected_source_date="20260904", expected_signal_date="20260907")


def test_validate_publication_receipt_rejects_tampered_selection(tmp_path: Path) -> None:
    artifact = _artifact()
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(artifact), encoding="utf-8")
    publication_path = _publication_receipt(artifact, selection_path)
    selection_path.write_text(json.dumps({**artifact, "content_sha256": "b" * 64}), encoding="utf-8")

    with pytest.raises(delivery.CashflowDeliveryError, match="selection_sha256"):
        delivery.validate_publication_receipt(
            publication_path, selection_path=selection_path, artifact=artifact
        )


def test_deliver_is_idempotent_and_writes_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(_artifact()), encoding="utf-8")
    receipt_path = tmp_path / "delivery-receipt.json"
    publication_path = _publication_receipt(_artifact(), selection_path)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        return type("Result", (), {"returncode": 0, "stdout": '{"ok":true,"data":{"message_id":"om_1"}}', "stderr": ""})()

    monkeypatch.setattr(delivery.subprocess, "run", fake_run)
    artifact = delivery.load_selection(
        selection_path,
        expected_source_date="20260904",
        expected_signal_date="20260907",
    )
    first = delivery.deliver(
        artifact=artifact,
        selection_path=selection_path,
        publication_receipt_path=publication_path,
        receipt_path=receipt_path,
        chat_ids=("oc_test",),
        lark_cli="lark-cli",
        dry_run=False,
    )
    second = delivery.deliver(
        artifact=artifact,
        selection_path=selection_path,
        publication_receipt_path=publication_path,
        receipt_path=receipt_path,
        chat_ids=("oc_test",),
        lark_cli="lark-cli",
        dry_run=False,
    )

    assert first["success"] is True
    assert second["targets"][0]["status"] == "already_sent"
    assert len(calls) == 1
    assert "--idempotency-key" in calls[0]


def test_deliver_rejects_previous_receipt_identity_drift(tmp_path: Path) -> None:
    artifact = _artifact()
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(artifact), encoding="utf-8")
    publication_path = _publication_receipt(artifact, selection_path)
    receipt_path = tmp_path / "delivery-receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": delivery.DELIVERY_SCHEMA,
                "strategy_id": artifact["strategy_id"],
                "policy_id": artifact["policy_id"],
                "signal_date": artifact["signal_date"],
                "content_sha256": "f" * 64,
                "selection_sha256": delivery._sha256_file(selection_path),
                "publication_receipt_sha256": delivery._sha256_file(publication_path),
                "targets": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(delivery.CashflowDeliveryError, match="identity mismatch"):
        delivery.deliver(
            artifact=artifact,
            selection_path=selection_path,
            publication_receipt_path=publication_path,
            receipt_path=receipt_path,
            chat_ids=("oc_test",),
            lark_cli="lark-cli",
            dry_run=True,
        )


def test_failure_receipt_is_alertable_and_retryable(tmp_path: Path) -> None:
    path = tmp_path / "delivery-receipt.json"
    delivery.write_failure_receipt(
        path,
        source_date="20260904",
        signal_date="20260907",
        error="publication receipt mismatch",
    )

    receipt = json.loads(path.read_text(encoding="utf-8"))

    assert receipt["status"] == "failed"
    assert receipt["success"] is False
    assert receipt["error"] == "publication receipt mismatch"

