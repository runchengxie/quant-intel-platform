"""Optional news survives the existing staged import without leaking private review."""

import json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256

import pytest

from a_share_daily.public_report_refresh import publish_batch
from market_intel_publication.asia_news_contract import build_public_asia_news
from market_intel_publication.import_reports import import_reports


def news_fixture(text):
    # Fully synthetic offline attestations; never used as live/source acceptance.
    from daily_messenger.daily_report.asia_news_contract import digest, validate_asia_candidate
    from daily_messenger.daily_report.asia_news_review import review_template

    candidate = validate_asia_candidate(
        {
            "schema_version": "market_intel.asia_news_candidate.v1",
            "collector_identity": "fixture-collector",
            "market": "cn",
            "source_url": "https://www.sse.com.cn/fixture",
            "publisher": "SSE",
            "published_at": "2026-09-30T14:00:00+08:00",
            "time_precision": "timestamp",
            "retrieved_at": "2026-09-30T18:00:00+08:00",
            "language": "zh-CN",
            "title": "fixture",
            "summary": "收入增长 6%。",
            "source_sha256": "a" * 64,
            "document_status": "active",
        }
    )
    receipt = review_template(candidate, cutoff=datetime.fromisoformat("2026-09-30T19:00:00+08:00"))
    receipt.update(
        status="approved",
        reviewer="fixture-reviewer",
        reviewed_at="2026-09-30T20:00:00+08:00",
        claim="收入增长 6%。",
        claim_sha256=digest("收入增长 6%。"),
        source_date_note="fixture",
        fact_note="fixture",
        rights_note="fixture",
        applicability_note="fixture",
        calendar={
            "market": "cn",
            "from": "2026-09-29",
            "through": "2026-09-30",
            "open_dates": ["2026-09-30"],
            "source_url": "https://www.sse.com.cn/calendar",
            "source_sha256": "b" * 64,
        },
    )
    return build_public_asia_news(
        [{"candidate": asdict(candidate), "review": receipt}],
        report_date="2026-09-30",
        generated_at="2026-09-30T20:30:00+08:00",
        report_sha256=sha256(text.encode()).hexdigest(),
    )


def site(root):
    public = root / "artifacts/public"
    (public / "data").mkdir(parents=True)
    (public / "reports").mkdir()
    (public / "data/reports.json").write_text(
        json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": []})
    )
    (public / "data/daily_summaries.json").write_text(
        json.dumps({"schema_version": "market_intel_pages.daily_summaries.v1", "summaries": []})
    )
    return public


def test_stage_preview_apply_and_correction_drop_stale_news(tmp_path):
    root, output, archive = (tmp_path / name for name in ("site", "output", "archive"))
    public = site(root)
    output.mkdir()
    stage = tmp_path / "batch"
    stage.mkdir()
    text = "# 收盘复盘\n生成时间: 2026-09-30 20:00\n## 盘面\n上涨 2567 家。\n"
    news = news_fixture(text)
    manifest = publish_batch(output, stage, {"evening": text}, "2026-09-30", asia_news=news)
    assert import_reports(root, manifest, archive)["applied"] is False
    assert not (public / "data/asia_news").exists()
    assert import_reports(root, manifest, archive, apply=True)["applied"] is True
    destination = public / "data/asia_news/2026-09-30-evening.json"
    assert json.loads(destination.read_text())["markets"]["cn"][0]["claim"] == "收入增长 6%。"
    assert list((archive / "asia_news_revisions").glob("*.json"))
    stage2 = tmp_path / "batch2"
    stage2.mkdir()
    correction = publish_batch(output, stage2, {"evening": text.replace("2567", "2568")}, "2026-09-30")
    import_reports(root, correction, archive, apply=True)
    assert not destination.exists()


def test_mismatched_report_rejected_before_public_writes(tmp_path):
    root, output, archive = (tmp_path / name for name in ("site", "output", "archive"))
    public = site(root)
    output.mkdir()
    stage = tmp_path / "batch"
    stage.mkdir()
    text = "# 收盘\n生成时间: 2026-09-30 20:00\n## 盘面\n行情。\n"
    with pytest.raises(ValueError):
        publish_batch(
            output, stage, {"evening": text}, "2026-09-30", asia_news=news_fixture(text + "changed")
        )
    assert not (output / "manifest.json").exists()
    assert json.loads((public / "data/reports.json").read_text())["reports"] == []
