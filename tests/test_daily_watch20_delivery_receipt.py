from __future__ import annotations

import json
from pathlib import Path

from a_share_daily.daily_watch20_delivery_receipt import (
    MessageAttempt,
    message_attempt,
    presentation,
    target_fingerprint,
    validate_delivery_receipt,
    write_delivery_receipt,
)


def _attempt(
    *,
    audience: str,
    medium: str,
    content_sha256: str,
) -> MessageAttempt:
    return MessageAttempt(
        audience=audience,
        target_sha256=target_fingerprint(f"oc_{audience}"),
        medium=medium,
        status="sent",
        idempotency_key=f"{audience}-{medium}",
        content_sha256=content_sha256,
        message_id=f"om_{audience}_{medium}",
        attempted_at="2026-07-29T00:00:00+00:00",
        error=None,
    )


def _write_complete_receipt(tmp_path: Path) -> Path:
    source_receipt = tmp_path / "selection_receipt.json"
    source_receipt.write_text('{"status":"passed"}\n', encoding="utf-8")
    presentations = []
    attempts = []
    for audience in ("client", "internal"):
        image = tmp_path / audience / "daily_watch20.png"
        html = tmp_path / audience / "daily_watch20.html"
        markdown = tmp_path / audience / "daily_watch20.md"
        image.parent.mkdir()
        image.write_bytes(f"{audience}-image".encode())
        html.write_text(f"<p>{audience}</p>", encoding="utf-8")
        markdown.write_text(f"# {audience}\n", encoding="utf-8")
        rendered = presentation(
            audience=audience,
            markdown=f"# {audience}\n",
            markdown_path=markdown,
            image_path=image,
            html_path=html,
        )
        presentations.append(rendered)
        attempts.extend(
            (
                _attempt(
                    audience=audience,
                    medium="markdown",
                    content_sha256=rendered.markdown_sha256,
                ),
                _attempt(
                    audience=audience,
                    medium="image",
                    content_sha256=rendered.image_sha256,
                ),
            )
        )
    path = tmp_path / "delivery_receipt.json"
    receipt = write_delivery_receipt(
        path=path,
        source_date="20260728",
        signal_date="20260729",
        source_receipt_path=source_receipt,
        presentations=presentations,
        attempts=attempts,
    )
    assert receipt["success"] is True
    return path


def test_message_attempt_requires_confirmed_message_id() -> None:
    confirmed = message_attempt(
        audience="client",
        chat_id="oc_client",
        medium="markdown",
        idempotency_key="key",
        content_sha256="a" * 64,
        returncode=0,
        stdout='{"ok":true,"data":{"message_id":"om_confirmed"}}',
        stderr="",
    )
    unconfirmed = message_attempt(
        audience="client",
        chat_id="oc_client",
        medium="markdown",
        idempotency_key="key",
        content_sha256="a" * 64,
        returncode=0,
        stdout="{}",
        stderr="",
    )

    assert confirmed.status == "sent"
    assert confirmed.message_id == "om_confirmed"
    assert unconfirmed.status == "failed"
    assert unconfirmed.message_id is None


def test_validate_delivery_receipt_accepts_complete_content_addressed_run(
    tmp_path: Path,
) -> None:
    path = _write_complete_receipt(tmp_path)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    Path(receipt["source_receipt_origin"]).write_text(
        '{"status":"next-day"}\n',
        encoding="utf-8",
    )

    problems = validate_delivery_receipt(
        path=path,
        expected_source_date="20260728",
        expected_signal_date="20260729",
        required_audiences=("client", "internal"),
    )

    assert problems == []
    assert Path(receipt["source_receipt_path"]).name == "source_selection_receipt.json"


def test_validate_delivery_receipt_rejects_artifact_drift_and_missing_audience(
    tmp_path: Path,
) -> None:
    path = _write_complete_receipt(tmp_path)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    Path(receipt["presentations"]["client"]["image_path"]).write_bytes(b"changed")
    receipt["targets"] = [target for target in receipt["targets"] if target["audience"] == "client"]
    path.write_text(json.dumps(receipt), encoding="utf-8")

    problems = validate_delivery_receipt(
        path=path,
        expected_source_date="20260728",
        expected_signal_date="20260729",
        required_audiences=("client", "internal"),
    )

    assert "client image 产物 hash 不一致" in problems
    assert "DailyWatch20 缺少完整投递 audience：internal" in problems
