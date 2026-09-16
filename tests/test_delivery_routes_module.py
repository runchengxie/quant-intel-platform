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
