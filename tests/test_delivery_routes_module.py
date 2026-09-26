from __future__ import annotations

from pathlib import Path

from a_share_daily.delivery import routes


def test_webhook_route_reports_success_for_all_text_files(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / "report.md"
    report.write_text("日报", encoding="utf-8")
    calls: list[Path] = []

    def fake_send(path: Path, *, title: str, enabled_env: str) -> bool:
        calls.append(path)
        return True

    monkeypatch.setattr(routes.senders, "_send_webhook_text", fake_send)

    status = routes.deliver_via_webhook(
        text_files=[(report, "标题", "日报")],
        routes_payload={},
        webhook_enabled_env="MORNING_SEND_WEBHOOK",
    )

    assert status is True
    assert calls == [report]


def test_morning_lark_route_records_preflight_and_message_ids(tmp_path: Path, monkeypatch) -> None:
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"png")
    context = routes.senders._DeliveryContext(
        mode="lark",
        chat_id="oc_test",
        user_id=None,
        hermes_target=None,
        hermes_cli=None,
        lark_cli="/bin/lark-cli",
        lark_targets=["oc_test"],
        hermes_targets=[],
    )
    calls: list[str] = []

    monkeypatch.setattr(
        routes.senders,
        "_ensure_lark_ready",
        lambda **kwargs: {"ok": True},
    )

    def send_text(*args, message_ids, **kwargs):
        calls.append("text")
        message_ids.append("msg-text")
        return True

    def send_image(*args, message_ids, **kwargs):
        calls.append("image")
        message_ids.append("msg-image")
        return True

    monkeypatch.setattr(routes.senders, "_send_lark_markdown", send_text)
    monkeypatch.setattr(routes.senders, "_send_lark_image", send_image)
    route_state: dict[str, object] = {}
    message_ids: dict[str, list[str]] = {}

    delivery = routes.MorningDeliveryContext(
        context=context,
        trade_date="20260926",
        signal_date="20260926",
        mode="lark",
        text="晨报内容",
        report_path=tmp_path / "morning.md",
        chart_paths=[chart],
        artifacts=[],
        routes_payload=route_state,
        message_ids=message_ids,
    )
    result = routes.deliver_morning_via_lark(delivery)

    assert result == (True, True)
    assert calls == ["text", "image"]
    assert route_state == {
        "lark_preflight": {"ok": True},
        "lark_text": True,
        "lark_images": True,
    }
    assert message_ids == {"lark_text": ["msg-text"], "lark_images": ["msg-image"]}


def test_morning_receipt_preserves_signal_and_route_metadata(monkeypatch) -> None:
    context = routes.senders._DeliveryContext(
        mode="both",
        chat_id="oc_test",
        user_id=None,
        hermes_target="feishu:oc_test",
        hermes_cli="/bin/hermes",
        lark_cli="/bin/lark-cli",
        lark_targets=["oc_test"],
        hermes_targets=["feishu:oc_test"],
    )
    delivery = routes.MorningDeliveryContext(
        context=context,
        trade_date="20260926",
        signal_date="20260925",
        mode="both",
        text="晨报内容",
        report_path=Path("morning.md"),
        chart_paths=[],
        artifacts=[{"role": "morning_report"}],
        routes_payload={"lark_text": True},
        message_ids={"lark_text": ["msg-1"]},
    )
    captured: dict[str, object] = {}

    def record_status(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(routes.state, "_write_delivery_status", record_status)

    routes.write_morning_delivery_status(delivery, success=False)

    assert captured == {
        "kind": "morning",
        "trade_date": "20260926",
        "signal_date": "20260925",
        "mode": "both",
        "success": False,
        "routes": {"lark_text": True},
        "artifacts": [{"role": "morning_report"}],
        "lark_targets": ["oc_test"],
        "hermes_targets": ["feishu:oc_test"],
        "message_ids": {"lark_text": ["msg-1"]},
    }
