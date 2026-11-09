"""Synthetic fixtures shared by public content transport tests."""

import hashlib
import importlib
import importlib.util
import json
import zipfile

from market_intel_publication.asia_news_contract import build_public_asia_news
from market_intel_publication.import_reports import parse_markdown
from market_intel_publication.us_daily_contract import _public_payload
from market_intel_publication.weekly_recap_bundle import import_bundle
from tests.test_weekly_recap_bundle import bundle, daily_root

REVISION = "a" * 40

CREATED = "2026-11-01T00:00:00Z"


def api(monkeypatch):
    assert importlib.util.find_spec("market_intel_publication.site_content_codec") is not None
    codec = importlib.import_module("market_intel_publication.site_content_codec")
    monkeypatch.setattr(
        codec,
        "installed_producer",
        lambda revision: {
            "owner": "quant-intel-platform",
            "distribution": "market-intel",
            "source_revision": revision,
            "source_sha256": "b" * 64,
        },
    )
    return codec


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def all_families(tmp_path):
    root = tmp_path / "source"
    public = daily_root(root)
    reports, us = [], []
    for day in ("2026-10-23", "2026-10-22", "2026-10-21", "2026-10-20", "2026-10-19"):
        text = f"# Public report\n\n## Market\n生成时间：{day} 20:00\nSynthetic facts.\n"
        row = parse_markdown(text, day, "evening")
        (public / row["source_url"]).write_text(text, encoding="utf-8")
        news = build_public_asia_news(
            [],
            report_date=day,
            generated_at=f"{day}T20:30:00+08:00",
            report_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        row["asia_news_sha256"] = news["content_sha256"]
        write(public / f"data/asia_news/{row['id']}.json", news)
        reports.append(row)
        from market_intel_publication.chart_contract import CHART_KEYS, SCHEMA

        chart = {
            "schema_version": SCHEMA,
            "publication": "public",
            "report_id": row["id"],
            "date": day,
            "kind": "evening",
            "generated_at": f"{day}T20:30:00+08:00",
            "charts": [
                {
                    "key": key,
                    "title": key,
                    "status": "missing",
                    "reason": "Synthetic missing",
                    "points": [],
                }
                for key in CHART_KEYS
            ],
        }
        chart["content_sha256"] = hashlib.sha256(
            json.dumps(chart, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        write(public / f"data/charts/{row['id']}.json", chart)
        raw = {
            "schema_version": "1.1" if day == "2026-10-22" else "1.0",
            "as_of": f"{day}T20:00:00Z",
            "generated_at": f"{day}T21:00:00Z",
            "run_id": f"daily-{day}",
            "facts": [],
            "events": [],
            "claims": [],
            "sections": [],
            "content_hash": "c" * 64,
        }
        projected = _public_payload(raw, {"report_sha256": "d" * 64})
        us.append(projected)
        for suffix in ("md", "txt"):
            (public / f"reports/{day}-market-daily.{suffix}").write_text("Synthetic public US\n")
    for week in ("2026-09-25", "2026-10-02", "2026-10-09", "2026-10-16", "2026-10-23"):
        weekly, _ = bundle(tmp_path / f"weekly-{week}", week)
        import_bundle(weekly, root)
    write(
        public / "data/reports.json",
        {"schema_version": "market_intel_pages.reports.v1", "reports": reports},
    )
    write(public / "data/market_daily_report.json", us[0])
    write(
        public / "data/market_daily_reports.json",
        {"schema_version": "market_intel_pages.us_daily_history.v1", "reports": us},
    )
    from market_intel_commentary.generate_daily_summary import summary_source_hash
    from market_intel_commentary.insight_contract import build_context

    context = build_context(reports, reports[0], reports[1])
    claim = {"text": "Synthetic interpretation.", "evidence_ids": [context["evidence"][0]["id"]]}
    note = {
        **context,
        "id": "synthetic-insight",
        "analysis": {"overview": claim, "changes": [claim], "tensions": [claim], "watchpoints": []},
    }
    write(
        public / "data/insights.json",
        {
            "schema_version": "market_intel_pages.insights.v1",
            "generation": {"status": "cached"},
            "insights": [note],
            "outcomes": [],
        },
    )
    summary = {
        "date": reports[0]["date"],
        "text": "Synthetic summary.",
        "morning_report_id": reports[0]["id"],
        "evening_report_id": reports[1]["id"],
        "source_hash": summary_source_hash(reports[0], reports[1]),
    }
    write(
        public / "data/daily_summaries.json",
        {"schema_version": "market_intel_pages.daily_summaries.v1", "summaries": [summary]},
    )
    return root


def pack(codec, root, target):
    return codec.pack_site_content(root, target, created_at_utc=CREATED, producer_revision=REVISION)


def verify(codec, archive, target):
    return codec.verify_site_content(
        archive,
        hashlib.sha256(archive.read_bytes()).hexdigest(),
        target,
        expected_producer_revision=REVISION,
    )


def rewrite(source, target, change):
    with zipfile.ZipFile(source) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    change(entries)
    with zipfile.ZipFile(target, "w") as archive:
        for info, data in entries:
            archive.writestr(info, data)
