from __future__ import annotations

from types import SimpleNamespace

import style_replica_bridge as bridge
from style_replica_bridge import delivery as delivery_mod
from style_replica_bridge import render as render_mod


def test_legacy_style_replica_delivery_requires_internal_ack(monkeypatch, capsys) -> None:
    monkeypatch.setenv(bridge.INTERNAL_FEISHU_USER_ENV, "ou_internal")

    def unexpected_run(*args, **kwargs):
        raise AssertionError("lark-cli must not run without internal acknowledgement")

    monkeypatch.setattr(delivery_mod.subprocess, "run", unexpected_run)

    assert not bridge.send_to_user(
        "internal report",
        user_id="ou_internal",
        lark_cli="lark-cli",
    )
    assert "internal-only" in capsys.readouterr().err


def test_legacy_style_replica_delivery_rejects_non_allowlisted_recipient(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv(bridge.INTERNAL_FEISHU_USER_ENV, "ou_internal")

    def unexpected_run(*args, **kwargs):
        raise AssertionError("lark-cli must not run for a non-allowlisted recipient")

    monkeypatch.setattr(delivery_mod.subprocess, "run", unexpected_run)

    assert not bridge.send_to_user(
        "internal report",
        user_id="ou_client",
        lark_cli="lark-cli",
        internal_delivery=True,
    )
    assert "not the internal allowlist" in capsys.readouterr().err


def test_legacy_style_replica_delivery_accepts_allowlisted_internal_recipient(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv(bridge.INTERNAL_FEISHU_USER_ENV, "ou_internal")

    def successful_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(delivery_mod.subprocess, "run", successful_run)

    assert bridge.send_to_user(
        "internal report",
        user_id="ou_internal",
        lark_cli="lark-cli",
        internal_delivery=True,
    )
    assert calls == [
        [
            "lark-cli",
            "im",
            "+messages-send",
            "--user-id",
            "ou_internal",
            "--markdown",
            "internal report",
        ]
    ]


def test_push_refuses_before_loading_or_rendering_without_internal_ack(monkeypatch) -> None:
    monkeypatch.setenv(bridge.INTERNAL_FEISHU_USER_ENV, "ou_internal")

    def unexpected_load(path):
        raise AssertionError("positions must not load before delivery authorization")

    monkeypatch.setattr(render_mod, "load_positions", unexpected_load)

    assert not bridge.push_daily_holdings(
        "positions.csv",
        user_id="ou_internal",
        internal_delivery=False,
    )


def test_legacy_style_replica_dry_run_remains_local(monkeypatch, capsys) -> None:
    monkeypatch.delenv(bridge.INTERNAL_FEISHU_USER_ENV, raising=False)

    def unexpected_run(*args, **kwargs):
        raise AssertionError("dry-run must not call lark-cli")

    monkeypatch.setattr(delivery_mod.subprocess, "run", unexpected_run)

    assert bridge.send_to_user("preview", dry_run=True)
    stdout = capsys.readouterr().out
    assert "INTERNAL-ONLY DRY RUN" in stdout


def test_push_fails_when_a_tearsheet_image_is_not_delivered(monkeypatch) -> None:
    from style_replica_bridge import tearsheet

    monkeypatch.setenv(bridge.INTERNAL_FEISHU_USER_ENV, "ou_internal")
    positions = bridge.pd.DataFrame({"symbol": ["000001.SZ"]})
    monkeypatch.setattr(render_mod, "load_positions", lambda path: positions)
    monkeypatch.setattr(render_mod, "enrich_positions_with_tags", lambda frame: frame)
    monkeypatch.setattr(
        tearsheet,
        "generate_tearsheet",
        lambda *args, **kwargs: {
            "html_report": "report.html",
            "industry_chart": "industry.png",
        },
    )
    monkeypatch.setattr(delivery_mod, "_send_lark_image", lambda *args, **kwargs: False)
    monkeypatch.setattr(render_mod, "format_holdings_summary", lambda *args: "summary")
    monkeypatch.setattr(delivery_mod, "send_to_user", lambda *args, **kwargs: True)

    assert not bridge.push_daily_holdings(
        "positions.csv",
        user_id="ou_internal",
        internal_delivery=True,
    )
