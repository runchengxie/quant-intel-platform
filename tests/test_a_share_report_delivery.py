from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from a_share_daily.delivery import io_util, report_delivery, senders, state, targets
from daily_messenger.tools import post_feishu


def test_delivery_project_root_resolves_repository_after_nested_refactor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MARKET_INTEL_ROOT", raising=False)
    assert io_util._project_root() == Path(__file__).resolve().parents[1]

    monkeypatch.setenv("MARKET_INTEL_ROOT", str(tmp_path))
    assert io_util._project_root() == tmp_path.resolve()


def _set_delivery_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(tmp_path / "delivery_state"))
    monkeypatch.setenv("A_SHARE_LARK_PREFLIGHT", "0")


def test_build_evening_summary_uses_structured_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    review = {
        "indices": {"000001.SH": {"name": "上证指数", "pct_chg": 0.8, "close": 3100.12}},
        "overview": {
            "median_pct_chg": 0.2,
            "wavg_pct_chg": 0.5,
            "turnover_total": 950000000.0,
            "breadth": {"up": 3200, "down": 1800, "up_ratio": 64.0},
            "vwap_above_ratio": 57.3,
            "down_limit_approx": 3,
        },
        "limits": {"limit_up": {"count": 45}, "max_board": 4},
        "moneyflow": {"northbound": {"north_net": 12_300_000_000}},
        "hot_sectors": {
            "top_by_change": [{"name": "半导体", "pct_change": 2.6}],
        },
    }
    news = {
        "markets": {
            "us": {
                "items": [
                    {
                        "title": "Fed update",
                        "summary": "美联储官员释放降息观察信号。",
                        "source": "Reuters",
                        "url": "https://example.com/fed",
                        "published_at": "2026-06-30",
                        "category": "macro",
                    }
                ]
            }
        }
    }
    manifest = {
        "cross_market": {
            "us_stocks": {
                "SPY": {"close": 610.1, "pct_chg": 0.3},
                "QQQ": {"close": 540.2, "pct_chg": -0.2},
                "SMH": {"close": 290.3, "pct_chg": 1.0},
            },
            "macros": {
                "^VIX": {"label": "VIX 恐慌指数", "close": 18.9, "pct_chg": 1.4},
            },
            "concept_mapping": [
                {
                    "concept": "半导体",
                    "avg_pct_chg": 1.5,
                    "signal": "bullish",
                    "drivers": ["SMH +1.0%"],
                }
            ],
        }
    }

    text = report_delivery.build_evening_summary(
        "20260630",
        review_payload=review,
        news_payload=news,
        manifest_payload=manifest,
        generated_at=datetime(2026, 6, 30, 18, 0),
    )

    assert "美股市场盘前 / 亚洲市场盘后（2026-06-30）" in text
    expected_headings = (
        "## 1. 市场温度",
        "## 2. 今日要闻",
        "## 3. 亚洲市场盘后复盘",
        "## 4. 美股盘前预览",
        "## 5. 跨市场传导",
        "## 6. 宏观环境",
        "## 7. 次日验证",
        "## 8. 数据质量",
    )
    positions = [text.index(heading) for heading in expected_headings]
    assert positions == sorted(positions)
    assert "市场温度数据不足；第 3 节仍保留原始市场事实" in text
    assert "Reuters" in text
    assert "A股中位数 +0.20%" in text
    assert "跌停（近似） 3 家" in text
    assert "SPY" in text
    assert "[OK] 半导体" in text
    assert "VIX 恐慌指数" in text
    assert "因子技术观察" not in text


def test_build_evening_summary_renders_ai_news_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = report_delivery.build_evening_summary(
        "20260630",
        review_payload={"overview": {}, "hot_sectors": {}},
        news_payload={
            "markets_requested": ["cn"],
            "disabled": False,
            "error": "AI news fetch failed or timed out",
            "markets": {"cn": {"error": "timeout after 45s"}},
        },
        manifest_payload={},
        generated_at=datetime(2026, 6, 30, 18, 0),
    )

    assert "未取得含 source/url/published_at 的结构化新闻条目" in text
    assert "AI news fetch failed or timed out" in text
    assert "A股: timeout after 45s" in text


def test_load_json_accepts_powershell_utf8_bom(tmp_path: Path) -> None:
    payload = tmp_path / "payload.json"
    payload.write_text('{"overview":{"breadth":{"up":1}}}', encoding="utf-8-sig")

    assert report_delivery._load_json(payload)["overview"]["breadth"]["up"] == 1


def test_smoke_delivery_mode_forces_none_unless_explicitly_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_INTEL_SMOKE_TEST", "1")
    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "auto")

    assert targets._delivery_mode() == "none"

    monkeypatch.setenv("MARKET_INTEL_ALLOW_SMOKE_SEND", "1")

    assert targets._delivery_mode() == "auto"


def test_deliver_evening_sends_two_texts_and_six_images_via_lark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n事实内容", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text('{"markets":{}}', encoding="utf-8")
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text('{"cross_market":{}}', encoding="utf-8")
    charts = []
    for _label, filename in io_util.EVENING_CHARTS:
        chart = out_dir / filename
        chart.write_bytes(b"png")
        charts.append(chart)

    calls: list[dict[str, Any]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": cmd, "cwd": cwd})
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "lark")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id="oc_test",
        user_id=None,
        lark_cli="/bin/echo",
    )

    assert report_delivery.deliver_evening(args) == 0
    assert len(calls) == 8
    assert calls[0]["cmd"][3:5] == ["--chat-id", "oc_test"]
    assert "--markdown" in calls[0]["cmd"]
    assert "--idempotency-key" in calls[0]["cmd"]
    assert "--markdown" in calls[1]["cmd"]
    text_keys = [call["cmd"][call["cmd"].index("--idempotency-key") + 1] for call in calls[:2]]
    assert text_keys == [
        state._idempotency_key(
            "markdown",
            "--chat-id",
            "oc_test",
            "evening",
            "20260630",
            "evening_summary.md",
        ),
        state._idempotency_key(
            "markdown",
            "--chat-id",
            "oc_test",
            "evening",
            "20260630",
            "evening_review.md",
        ),
    ]
    assert all("--image" in call["cmd"] for call in calls[2:])
    assert [Path(call["cwd"] or "") for call in calls[2:]] == [out_dir] * 6
    assert (out_dir / "evening_summary.md").exists()


def test_deliver_morning_segmented_targets_internal_group_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report = out_dir / "morning_report.md"
    report.write_text("# 晨报\n亚洲市场盘前信息", encoding="utf-8")
    manifest = out_dir / "morning_manifest.json"
    manifest.write_text('{"date":"20260630","charts":{"paths":{},"skipped":[]}}', encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "lark")
    monkeypatch.setenv("MARKET_INTEL_CLIENT_CHAT_ID", "oc_client")
    monkeypatch.setenv("MARKET_INTEL_INTERNAL_CHAT_ID", "oc_internal")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        report=str(report),
        manifest=str(manifest),
        chat_id=None,
        user_id=None,
        hermes_target=None,
        hermes_cli=None,
        lark_cli="/bin/echo",
    )

    assert report_delivery.deliver_morning(args) == 0
    assert [call[call.index("--chat-id") + 1] for call in calls] == ["oc_internal"]


def test_deliver_evening_segmented_targets_split_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n亚洲盘后复盘", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text(
        json.dumps(
            {
                "markets": {
                    "us": {
                        "items": [
                            {
                                "title": "Fed",
                                "summary": "美股盘前新闻",
                                "source": "Reuters",
                                "url": "https://example.com/fed",
                                "published_at": "2026-06-30",
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text(
        '{"date":"20260630","charts":{"paths":{},"skipped":[]},"cross_market":{}}', encoding="utf-8"
    )
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "lark")
    monkeypatch.setenv("MARKET_INTEL_CLIENT_CHAT_ID", "oc_client")
    monkeypatch.setenv("MARKET_INTEL_INTERNAL_CHAT_ID", "oc_internal")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id=None,
        user_id=None,
        hermes_target=None,
        hermes_cli=None,
        lark_cli="/bin/echo",
    )

    assert report_delivery.deliver_evening(args) == 0
    targets = [call[call.index("--chat-id") + 1] for call in calls]
    markdowns = [call[call.index("--markdown") + 1] for call in calls]
    assert targets == ["oc_client", "oc_internal", "oc_internal"]
    assert "亚洲盘后复盘" in markdowns[0]
    assert "Reuters" not in markdowns[0]
    assert "Reuters" in markdowns[1]
    assert "亚洲盘后复盘" in markdowns[2]


def test_deliver_evening_uses_manifest_chart_paths_instead_of_stale_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n事实内容", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text('{"markets":{}}', encoding="utf-8")
    for _label, filename in io_util.EVENING_CHARTS:
        (out_dir / filename).write_bytes(b"stale")
    dashboard = out_dir / "fresh_dashboard.png"
    sentiment = out_dir / "fresh_sentiment.png"
    us_overnight = out_dir / "fresh_us_overnight.png"
    weekly_chart = out_dir / "fresh_weekly_chart.png"
    dashboard.write_bytes(b"fresh")
    sentiment.write_bytes(b"fresh")
    us_overnight.write_bytes(b"fresh")
    weekly_chart.write_bytes(b"fresh")
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "charts": {
                    "paths": {
                        "dashboard": str(dashboard),
                        "moneyflow": None,
                        "topic": None,
                        "sentiment": str(sentiment),
                        "us_overnight": str(us_overnight),
                        "weekly_chart": str(weekly_chart),
                    },
                    "skipped": ["moneyflow", "topic"],
                },
                "cross_market": {},
            }
        ),
        encoding="utf-8",
    )

    calls: list[dict[str, Any]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": cmd, "cwd": cwd})
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "lark")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id="oc_test",
        user_id=None,
        lark_cli="/bin/echo",
    )

    assert report_delivery.deliver_evening(args) == 0
    image_calls = [call for call in calls if "--image" in call["cmd"]]
    assert len(image_calls) == 4
    assert [call["cmd"][call["cmd"].index("--image") + 1] for call in image_calls] == [
        dashboard.name,
        sentiment.name,
        us_overnight.name,
        weekly_chart.name,
    ]
    assert "chart missing from manifest" not in capsys.readouterr().err


def test_manifest_chart_paths_resolve_project_relative_output_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "out" / "a_share_daily"
    out_dir.mkdir(parents=True)
    dashboard = out_dir / "fresh_dashboard.png"
    dashboard.write_bytes(b"fresh")
    manifest_path = out_dir / "evening_manifest.json"
    manifest = {
        "date": "20260630",
        "charts": {
            "paths": {
                "dashboard": "out/a_share_daily/fresh_dashboard.png",
                "moneyflow": None,
                "topic": None,
                "sentiment": None,
            },
            "skipped": ["moneyflow", "topic", "sentiment", "us_overnight", "weekly_chart"],
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(io_util, "PROJECT_ROOT", tmp_path)

    paths = report_delivery._chart_paths(
        out_dir,
        manifest=manifest,
        manifest_path=manifest_path,
        expected_date="20260630",
    )

    assert paths == [dashboard.resolve()]


def test_send_morning_charts_uses_manifest_available_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    manifest_path = out_dir / "morning_manifest.json"
    manifest = {
        "charts": {
            "paths": {
                "dashboard": str(out_dir / "daily_dashboard.png"),
                "moneyflow": str(out_dir / "daily_moneyflow_chart.png"),
                "topic": str(out_dir / "daily_topic_chart.png"),
                "sentiment": None,
                "us_overnight": str(out_dir / "daily_us_overnight.png"),
                "weekly_chart": str(out_dir / "daily_weekly_chart.png"),
                "weekly_text": str(out_dir / "weekly_recap.md"),
            },
            "skipped": ["sentiment"],
        }
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    for filename in (
        "daily_dashboard.png",
        "daily_moneyflow_chart.png",
        "daily_topic_chart.png",
        "daily_us_overnight.png",
        "daily_weekly_chart.png",
    ):
        (out_dir / filename).write_bytes(b"png")

    sent: list[str] = []

    def fake_send_hermes_image(
        image: Path,
        *,
        chat_id: str | None = None,
        target: str | None = None,
        hermes_cli: str | None = None,
    ) -> bool:
        sent.append(image.name)
        return True

    monkeypatch.setattr(senders, "_send_hermes_image", fake_send_hermes_image)

    report_delivery._send_morning_charts(
        out_dir,
        manifest=manifest,
        manifest_path=manifest_path,
    )

    assert sent == [
        "daily_dashboard.png",
        "daily_moneyflow_chart.png",
        "daily_topic_chart.png",
        "daily_us_overnight.png",
        "daily_weekly_chart.png",
    ]


def test_default_chart_paths_skip_images_older_than_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    dashboard = out_dir / "daily_dashboard.png"
    dashboard.write_bytes(b"stale")
    manifest_path = out_dir / "evening_manifest.json"
    manifest_path.write_text('{"cross_market":{}}', encoding="utf-8")
    old_mtime = manifest_path.stat().st_mtime - 7200
    os.utime(dashboard, (old_mtime, old_mtime))

    paths = report_delivery._chart_paths(out_dir, manifest={}, manifest_path=manifest_path)

    assert paths == []
    assert "chart stale relative to manifest" in capsys.readouterr().err


def test_deliver_evening_sends_files_and_absolute_media_via_hermes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n事实内容", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text('{"markets":{}}', encoding="utf-8")
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text('{"cross_market":{}}', encoding="utf-8")
    for _label, filename in io_util.EVENING_CHARTS:
        (out_dir / filename).write_bytes(b"png")

    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "hermes")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id="oc_test",
        user_id=None,
        hermes_target="feishu:oc_test",
        hermes_cli="/bin/echo",
        lark_cli=None,
    )

    assert report_delivery.deliver_evening(args) == 0
    assert len(calls) == 8
    assert all(call[:4] == ["/bin/echo", "send", "--to", "feishu:oc_test"] for call in calls)
    assert all("--file" in call for call in calls[:2])
    media_args = [arg for call in calls[2:] for arg in call if arg.startswith("MEDIA:")]
    assert len(media_args) == 6
    assert all(Path(arg.removeprefix("MEDIA:")).is_absolute() for arg in media_args)


def test_deliver_evening_sends_each_payload_to_multiple_hermes_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n事实内容", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text('{"markets":{}}', encoding="utf-8")
    for filename in ("daily_dashboard.png", "daily_sentiment_chart.png"):
        (out_dir / filename).write_bytes(b"png")
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "charts": {
                    "paths": {
                        "dashboard": str(out_dir / "daily_dashboard.png"),
                        "sentiment": str(out_dir / "daily_sentiment_chart.png"),
                        "moneyflow": None,
                        "topic": None,
                    },
                    "skipped": ["moneyflow", "topic", "us_overnight", "weekly_chart"],
                },
                "cross_market": {},
            }
        ),
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "hermes")
    monkeypatch.setenv("A_SHARE_HERMES_TARGET", "feishu:oc_one,feishu:oc_two;feishu:oc_three")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id=None,
        user_id=None,
        hermes_target=None,
        hermes_cli="/bin/echo",
        lark_cli=None,
    )

    assert report_delivery.deliver_evening(args) == 0
    assert len(calls) == 12
    targets = [call[call.index("--to") + 1] for call in calls]
    assert targets.count("feishu:oc_one") == 4
    assert targets.count("feishu:oc_two") == 4
    assert targets.count("feishu:oc_three") == 4


def test_lark_markdown_sends_to_multiple_chat_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_one,oc_two")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    assert senders._send_lark_markdown("日报", lark_cli="/bin/echo")
    assert [call[call.index("--chat-id") + 1] for call in calls] == ["oc_one", "oc_two"]


def test_hermes_targets_prefer_current_chat_id_over_global_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("A_SHARE_HERMES_TARGET", "feishu:oc_legacy")

    assert targets._hermes_targets(chat_id="oc_internal") == ["feishu:oc_internal"]


def test_lark_preflight_rebinds_from_hermes_when_whoami_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": cmd, "env": env or {}})
        if (
            cmd[1:] == ["whoami"]
            and len([call for call in calls if call["cmd"][1:] == ["whoami"]]) == 1
        ):
            return subprocess.CompletedProcess(
                cmd,
                0,
                '{"identity":"bot","available":false,"tokenStatus":"missing"}',
                "",
            )
        if cmd[1:] == ["config", "bind", "--source", "hermes", "--identity", "bot-only"]:
            return subprocess.CompletedProcess(cmd, 0, '{"ok":true}', "")
        return subprocess.CompletedProcess(
            cmd,
            0,
            '{"identity":"bot","available":true,"tokenStatus":"ready"}',
            "",
        )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    status = senders._ensure_lark_ready(lark_cli="/bin/lark-cli", has_targets=True)

    assert status["ok"] is True
    assert status["bind_attempted"] is True
    assert status["bind_ok"] is True
    assert status["reason"] == "ready_after_bind"
    bind_call = next(call for call in calls if call["cmd"][1:3] == ["config", "bind"])
    assert bind_call["env"]["HERMES_HOME"] == str(tmp_path / "localappdata" / "hermes")


def test_deliver_morning_records_lark_preflight_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "delivery_state"
    monkeypatch.setenv("A_SHARE_DELIVERY_STATE_DIR", str(state_dir))
    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "lark")
    monkeypatch.setenv("A_SHARE_FEISHU_CHAT_ID", "oc_test")
    report = tmp_path / "morning_report.md"
    report.write_text("# 晨报\n事实内容", encoding="utf-8")

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if cmd[1:] == ["whoami"]:
            return subprocess.CompletedProcess(cmd, 1, "", "not configured")
        if cmd[1:3] == ["config", "bind"]:
            return subprocess.CompletedProcess(cmd, 1, "", "bind failed")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        report=str(report),
        chat_id=None,
        user_id=None,
        hermes_target=None,
        hermes_cli=None,
        lark_cli="/bin/lark-cli",
    )

    assert report_delivery.deliver_morning(args) == 1
    state = json.loads((state_dir / "morning_latest.json").read_text(encoding="utf-8"))
    assert state["success"] is False
    assert state["routes"]["lark_text"] is False
    assert state["routes"]["lark_preflight"]["bind_attempted"] is True
    assert state["routes"]["lark_preflight"]["reason"] == "bind_returned_1"


def test_deliver_evening_falls_back_to_hermes_images_only_when_lark_images_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    review = out_dir / "evening_review.md"
    review.write_text("## 完整盘后数据\n事实内容", encoding="utf-8")
    review_json = out_dir / "evening_review.json"
    review_json.write_text('{"overview":{"breadth":{}}}', encoding="utf-8")
    news = out_dir / "ai_market_news_evening.json"
    news.write_text('{"markets":{}}', encoding="utf-8")
    manifest = out_dir / "evening_manifest.json"
    manifest.write_text('{"cross_market":{}}', encoding="utf-8")
    for _label, filename in io_util.EVENING_CHARTS:
        (out_dir / filename).write_bytes(b"png")

    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        cwd: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[1:3] == ["im", "+messages-send"] and "--msg-type" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "lark image upload failed")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "auto")
    monkeypatch.setattr(report_delivery.subprocess, "run", fake_run)

    args = argparse.Namespace(
        date="20260630",
        out_dir=str(out_dir),
        summary_out=str(out_dir / "evening_summary.md"),
        review=str(review),
        review_json=str(review_json),
        news=str(news),
        manifest=str(manifest),
        chart=None,
        chat_id="oc_test",
        user_id=None,
        hermes_target="feishu:oc_test",
        hermes_cli="/bin/echo",
        lark_cli="/bin/echo",
    )

    assert report_delivery.deliver_evening(args) == 0
    hermes_calls = [call for call in calls if call[1] == "send"]
    lark_calls = [call for call in calls if call[1] == "im"]
    assert len(lark_calls) == 8
    assert len(hermes_calls) == 6
    assert all("--msg-type" in call and "image" in call for call in lark_calls[2:])
    assert all(any(arg.startswith("MEDIA:") for arg in call) for call in hermes_calls)
    assert not any("--file" in call for call in hermes_calls)


def test_deliver_morning_falls_back_to_webhook_without_lark_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_delivery_state(monkeypatch, tmp_path)
    report = tmp_path / "morning_report.md"
    report.write_text("# 晨报\n事实内容", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_post(argv: list[str] | None = None) -> int:
        assert argv is not None
        calls.append(argv)
        return 0

    monkeypatch.setenv("A_SHARE_REPORT_DELIVERY", "auto")
    monkeypatch.delenv("A_SHARE_HERMES_TARGET", raising=False)
    monkeypatch.delenv("HERMES_SEND_TARGET", raising=False)
    monkeypatch.delenv("A_SHARE_FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("FEISHU_CHAT_ID", raising=False)
    monkeypatch.delenv("A_SHARE_FEISHU_USER_ID", raising=False)
    monkeypatch.delenv("FEISHU_USER_ID", raising=False)
    monkeypatch.setattr(post_feishu, "run", fake_post)

    args = argparse.Namespace(
        report=str(report),
        chat_id=None,
        user_id=None,
        hermes_target=None,
        hermes_cli=None,
        lark_cli="/bin/echo",
    )

    assert report_delivery.deliver_morning(args) == 0
    assert len(calls) == 1
    assert "--summary" in calls[0]
    assert str(report) in calls[0]
