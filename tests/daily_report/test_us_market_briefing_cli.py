from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def manifest_path() -> Path:
    return (
        Path(__file__).parents[1]
        / "fixtures"
        / "publications"
        / "us_market_briefing"
        / "publication-manifest.json"
    )


def test_renderer_preserves_text_and_lists_source_links(manifest_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import (
        load_us_market_briefing_bundle,
        render_us_market_briefing,
    )

    bundle = load_us_market_briefing_bundle(manifest_path, allow_internal=True)

    rendered = render_us_market_briefing(bundle)

    assert rendered.startswith(bundle.briefing["headline"])
    assert bundle.briefing["brief_text"] in rendered
    source = bundle.briefing["sources"][0]
    assert f"{source['title']}（{source['publisher']}）：{source['url']}" in rendered


def test_cli_emits_offline_preview_without_loading_destinations_or_sending(
    manifest_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from daily_messenger import cli

    def forbidden(*args, **kwargs):
        raise AssertionError("preview must not send or read destination config")

    monkeypatch.setenv("MARKET_INTEL_US_BRIEFING_CHAT_IDS", "synthetic-chat")
    monkeypatch.setenv("FEISHU_WEBHOOK_DAILY", "https://example.com/never-send")
    monkeypatch.setenv("LARK_CLI", "never-run")
    monkeypatch.setattr(cli, "_load_runtime_env_files", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr("requests.post", forbidden)

    exit_code = cli.main(
        ["us-briefing-preview", "--manifest", str(manifest_path), "--allow-internal"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["schema_version"] == "market.briefing.preview.v1"
    assert payload["status"] == "preview"
    assert payload["dry_run"] is True
    assert payload["market_date"] == "2099-01-02"
    assert payload["run_id"] == "us-2099-01-02-close-r1"
    assert payload["revision"] == 1
    assert payload["audience"] == "internal"
    assert payload["brief_text"] == "\n\n".join(
        paragraph["text"]
        for paragraph in json.loads(
            (manifest_path.parent / "briefing.json").read_text(encoding="utf-8")
        )["paragraphs"]
    )
    assert payload["sources"][0]["url"] == "https://example.com/synthetic-us-market-briefing"
    assert payload["rendered_text"].startswith(payload["headline"])
    assert payload["brief_text"] in payload["rendered_text"]


def test_cli_rejects_internal_bundle_without_opt_in(
    manifest_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from daily_messenger import cli

    exit_code = cli.main(["us-briefing-preview", "--manifest", str(manifest_path)])

    assert exit_code == 2
    assert '"schema_version": "market.briefing.preview.v1"' not in capsys.readouterr().out


def test_preview_render_has_no_delivery_time_fields(manifest_path: Path) -> None:
    from daily_messenger.daily_report.us_market_briefing import (
        load_us_market_briefing_bundle,
        make_us_market_briefing_preview,
    )

    bundle = load_us_market_briefing_bundle(manifest_path, allow_internal=True)

    preview = make_us_market_briefing_preview(bundle)

    assert preview["dry_run"] is True
    assert "target" not in preview
    assert "message_id" not in preview
