import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

import scripts.build_site as build_site_module
from scripts.build_site import _copy_daily_report_formats, build_site, refresh_astro
from scripts.sync_public_snapshot import sync_snapshot
from tests.test_chart_contract import public_chart, rehash
from tests.test_import_market_daily_report import _cross_asset_payload

REPORT_SCHEMA = "market_intel_pages.reports.v1"
SUMMARY_SCHEMA = "market_intel_pages.daily_summaries.v1"


def test_build_cli_resolves_owner_without_an_editable_install():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-S", "scripts/build_site.py", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_supported_build_stages_bound_asia_news_before_astro(tmp_path, monkeypatch):
    from market_intel_publication.import_reports import parse_markdown

    from tests.test_asia_news_import import news_fixture

    root, output = tmp_path / "source", tmp_path / "site"
    create_site(root, 1)
    public = root / "artifacts/public"
    text = "# 收盘复盘\n生成时间: 2026-09-30 20:00\n## 盘面\n上涨 2567 家。\n"
    row = parse_markdown(text, "2026-09-30", "evening")
    (public / row["source_url"]).write_text(text)
    (public / "data/reports.json").write_text(json.dumps({"schema_version": REPORT_SCHEMA, "reports": [row]}))
    news = news_fixture(text)
    (public / "data/asia_news").mkdir()
    (public / "data/asia_news/2026-09-30-evening.json").write_text(json.dumps(news))
    observed = []

    def astro(_root, stage, _ids):
        observed.append(json.loads((stage / "data/asia_news/2026-09-30-evening.json").read_text()))

    monkeypatch.setattr(build_site_module, "_overlay_astro_pages", astro)
    build_site(root, output)
    assert observed == [news]
    (public / row["source_url"]).write_text(text + "correction")
    with pytest.raises(ValueError):
        build_site(root, output)
    assert json.loads((output / "data/asia_news/2026-09-30-evening.json").read_text()) == news


def test_supported_build_renders_synthetic_reviewed_news_in_both_locales(tmp_path):
    from daily_messenger.daily_report.asia_news_contract import digest
    from market_intel_publication.import_reports import parse_markdown

    from tests.test_asia_news_import import news_fixture

    actual = Path(__file__).resolve().parents[1]
    root, output = tmp_path / "source", tmp_path / "site"
    create_site(root, 1)
    shutil.copytree(actual / "src", root / "src", dirs_exist_ok=True)
    for name in ("package.json", "astro.config.mjs", "tsconfig.json"):
        shutil.copy2(actual / name, root / name)
    (root / "node_modules").symlink_to(actual / "node_modules", target_is_directory=True)
    public = root / "artifacts/public"
    text = "# 收盘复盘\n生成时间: 2026-09-30 20:00\n## 盘面\n上涨 2567 家。\n"
    row = parse_markdown(text, "2026-09-30", "evening")
    (public / row["source_url"]).write_text(text)
    (public / "data/reports.json").write_text(json.dumps({"schema_version": REPORT_SCHEMA, "reports": [row]}))
    news = news_fixture(text, english=True)
    news["markets"]["hk"] = news_fixture(text, "hk", english=True)["markets"]["hk"]
    news["content_sha256"] = digest({k: v for k, v in news.items() if k != "content_sha256"})
    (public / "data/asia_news").mkdir()
    (public / "data/asia_news/2026-09-30-evening.json").write_text(json.dumps(news))
    build_site(root, output)
    for route, claim in (("index.html", "收入增长 6%。"), ("en/index.html", "Revenue rose 6%.")):
        html = (output / route).read_text()
        assert html.count(claim) == 2
        assert "https://www.sse.com.cn/fixture" in html
        assert "https://www.hkexnews.hk/fixture" in html
        assert "HKEXnews" in html and "2026" in html
        if route.startswith("en/"):
            assert html.index(claim) < html.index("Market interpretation and validation")
    assert "fixture-reviewer" not in (output / "data/asia_news/2026-09-30-evening.json").read_text()


def test_evening_only_summary_is_validated_by_report_date() -> None:
    rows = [
        {"id": "old", "kind": "evening", "date": "2026-09-23"},
        {"id": "new", "kind": "evening", "date": "2026-09-24"},
    ]
    summary = {"date": "2026-09-24", "morning_report_id": "new", "evening_report_id": "old"}
    build_site_module._validate(rows, [summary])
    with pytest.raises(ValueError, match="baseline"):
        build_site_module._validate(rows, [{**summary, "evening_report_id": "new"}])


def test_new_public_copy_cannot_reuse_legacy_continuous_commodity_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[1]
    payload = _cross_asset_payload()
    payload["publication"] = "public"
    payload["report_formats"] = []
    for fact in payload["facts"]:
        if fact["id"].startswith("cross_asset.brent."):
            fact["source_url"] = "https://finance.yahoo.com/quote/BZ%3DF/history/"
            fact["instrument"] = "Brent continuous futures (BZ=F)"
    projection_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    monkeypatch.setattr(build_site_module, "LEGACY_CONTINUOUS_REPORT_HASHES", {projection_hash})
    published_hash = payload["content_hash"]
    output = tmp_path / "site"
    (output / "reports").mkdir(parents=True)
    _copy_daily_report_formats(root, output, payload)

    payload["content_hash"] = "different-new-report-hash"
    with pytest.raises(ValueError, match="invalid sourced market fact"):
        _copy_daily_report_formats(root, output, payload)

    payload["content_hash"] = published_hash
    next(fact for fact in payload["facts"] if fact["id"] == "cross_asset.brent.close")["value"] += 1
    with pytest.raises(ValueError, match="invalid sourced market fact"):
        _copy_daily_report_formats(root, output, payload)


def create_site(root: Path, session_count: int = 6) -> None:
    public_root = root / "artifacts/public"
    (public_root / "data").mkdir(parents=True)
    (public_root / "reports").mkdir()
    (root / "src/legacy").mkdir(parents=True)
    (root / "src/lib").mkdir(parents=True)
    for name in (
        "index.html",
        "app.js",
        "styles.css",
        "summary-utils.js",
        "report-markdown.js",
        "theme-utils.js",
    ):
        (root / "src/legacy" / name).write_text(name, encoding="utf-8")
    (root / "src/lib/market-daily-utils.js").write_text("market-daily-utils.js", encoding="utf-8")

    reports = []
    for day in range(1, session_count + 1):
        date = f"2026-09-{day:02d}"
        for kind in ("morning", "evening"):
            report_id = f"{date}-{kind}"
            source_url = f"reports/{report_id}.md"
            reports.append(
                {
                    "id": report_id,
                    "date": date,
                    "kind": kind,
                    "title": report_id,
                    "summary": "sample",
                    "sections": [],
                    "source_url": source_url,
                }
            )
            (public_root / source_url).write_text(f"# {report_id}\n", encoding="utf-8")

    (public_root / "data/reports.json").write_text(
        json.dumps(
            {
                "schema_version": REPORT_SCHEMA,
                "generated_at": "2026-09-16T08:00:00+08:00",
                "reports": reports,
            }
        ),
        encoding="utf-8",
    )
    (public_root / "data/daily_summaries.json").write_text(
        json.dumps(
            {
                "schema_version": SUMMARY_SCHEMA,
                "summaries": [],
            }
        ),
        encoding="utf-8",
    )


class BuildSiteTests(unittest.TestCase):
    def test_build_copies_only_indexed_public_charts(self) -> None:
        sync_snapshot(self.root, self.archive)
        chart_dir = self.root / "artifacts/public/data/charts"
        chart_dir.mkdir()
        current = public_chart()
        current["date"] = "2026-09-02"
        current["report_id"] = "2026-09-02-morning"
        current["charts"][0]["points"][0]["observation_date"] = "2026-09-02"
        (chart_dir / "2026-09-02-morning.json").write_text(json.dumps(rehash(current)), encoding="utf-8")
        (chart_dir / "2026-09-01-morning.json").write_text("stale private data", encoding="utf-8")
        build_site(self.root, self.output)
        self.assertTrue((self.output / "data/charts/2026-09-02-morning.json").is_file())
        self.assertFalse((self.output / "data/charts/2026-09-01-morning.json").exists())
        self.assertTrue((self.output / "legacy/index.html").is_file())
        self.assertTrue((self.output / "legacy/market-daily-utils.js").is_file())

    def test_build_rejects_candidate_chart_in_current_window(self) -> None:
        sync_snapshot(self.root, self.archive)
        chart_dir = self.root / "artifacts/public/data/charts"
        chart_dir.mkdir()
        current = public_chart()
        current["date"] = "2026-09-02"
        current["report_id"] = "2026-09-02-morning"
        current["publication"] = "candidate"
        current["charts"][0]["points"][0]["observation_date"] = "2026-09-02"
        (chart_dir / "2026-09-02-morning.json").write_text(json.dumps(rehash(current)), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "public"):
            build_site(self.root, self.output)

    def test_failed_build_preserves_previous_artifact(self) -> None:
        sync_snapshot(self.root, self.archive)
        build_site(self.root, self.output)
        (self.output / "index.html").write_text("published artifact", encoding="utf-8")
        (self.root / "artifacts/public/data/charts").mkdir()
        (self.root / "artifacts/public/data/charts/2026-09-02-morning.json").write_text(
            '{"publication":"candidate"}'
        )
        with self.assertRaises(ValueError):
            build_site(self.root, self.output)
        self.assertEqual("published artifact", (self.output / "index.html").read_text(encoding="utf-8"))

    def test_build_emits_health_and_optional_insights(self) -> None:
        sync_snapshot(self.root, self.archive)
        build_site(self.root, self.output)
        health = json.loads((self.output / "data/health.json").read_text())
        self.assertEqual("missing", health["status"])
        self.assertEqual(
            "market_intel_pages.insights.v1",
            json.loads((self.output / "data/insights.json").read_text())["schema_version"],
        )

    def test_build_copies_imported_market_daily_data(self) -> None:
        sync_snapshot(self.root, self.archive)
        payload = {"schema_version": "1.0", "run_id": "daily-2026-09-23"}
        (self.root / "artifacts/public/data/market_daily_report.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        (self.root / "artifacts/public/reports/2026-09-23-market-daily.txt").write_text(
            "verified text\n", encoding="utf-8"
        )
        (self.root / "artifacts/public/reports/2026-09-23-market-daily.md").write_text(
            "# verified markdown\n", encoding="utf-8"
        )
        (self.root / "artifacts/public/reports/2026-09-22-market-daily.txt").write_text(
            "stale\n", encoding="utf-8"
        )
        build_site(self.root, self.output)
        self.assertEqual(
            payload,
            json.loads((self.output / "data/market_daily_report.json").read_text()),
        )
        self.assertEqual(
            "verified text\n",
            (self.output / "reports/2026-09-23-market-daily.txt").read_text(),
        )
        self.assertTrue((self.output / "reports/2026-09-23-market-daily.md").is_file())
        self.assertFalse((self.output / "reports/2026-09-22-market-daily.txt").exists())

    def test_build_copies_five_us_daily_history_reports(self) -> None:
        sync_snapshot(self.root, self.archive)
        rows = []
        for day in ("2026-09-23", "2026-09-24"):
            rows.append({"schema_version": "1.0", "run_id": f"daily-{day}", "report_formats": ["md", "txt"]})
            (self.root / f"artifacts/public/reports/{day}-market-daily.md").write_text(f"# {day}\n")
            (self.root / f"artifacts/public/reports/{day}-market-daily.txt").write_text(f"{day}\n")
        (self.root / "artifacts/public/data/market_daily_report.json").write_text(json.dumps(rows[-1]))
        (self.root / "artifacts/public/data/market_daily_reports.json").write_text(
            json.dumps(
                {
                    "schema_version": "market_intel_pages.us_daily_history.v1",
                    "reports": rows[::-1],
                }
            )
        )

        build_site(self.root, self.output)

        self.assertTrue((self.output / "reports/2026-09-23-market-daily.md").is_file())
        history = json.loads((self.output / "data/market_daily_reports.json").read_text())
        self.assertEqual(
            ["daily-2026-09-24", "daily-2026-09-23"], [row["run_id"] for row in history["reports"]]
        )

    def test_build_rejects_claimed_text_format_without_file(self) -> None:
        sync_snapshot(self.root, self.archive)
        (self.root / "artifacts/public/data/market_daily_report.json").write_text(
            json.dumps({"run_id": "daily-2026-09-23", "report_formats": ["md", "txt"]}),
            encoding="utf-8",
        )
        (self.root / "artifacts/public/reports/2026-09-23-market-daily.md").write_text("# report\n")
        with self.assertRaisesRegex(ValueError, "claimed market daily format missing"):
            build_site(self.root, self.output)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.root = self.directory / "repo"
        self.archive = self.directory / "local-archive"
        self.output = self.directory / "site"
        create_site(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_sync_keeps_all_reports_locally_and_only_five_dates_public(self) -> None:
        sync_snapshot(self.root, self.archive)

        local = json.loads((self.archive / "data/reports.json").read_text())
        public = json.loads((self.root / "artifacts/public/data/reports.json").read_text())
        self.assertEqual(12, len(local["reports"]))
        self.assertEqual(10, len(public["reports"]))
        self.assertEqual("2026-09-02", min(r["date"] for r in public["reports"]))
        self.assertTrue((self.archive / "reports/2026-09-01-morning.md").exists())
        self.assertFalse((self.root / "artifacts/public/reports/2026-09-01-morning.md").exists())

    def test_sync_is_idempotent_for_report_ids(self) -> None:
        sync_snapshot(self.root, self.archive)
        sync_snapshot(self.root, self.archive)

        local = json.loads((self.archive / "data/reports.json").read_text())
        self.assertEqual(12, len(local["reports"]))

    def test_sync_preserves_distinct_summary_source_pairs(self) -> None:
        summaries = []
        for evening_id in ("2026-09-05-evening", "2026-09-06-evening"):
            summaries.append(
                {
                    "date": "2026-09-06",
                    "text": f"note from {evening_id}",
                    "morning_report_id": "2026-09-06-morning",
                    "evening_report_id": evening_id,
                    "generated_at": "2026-09-07T07:00:00+08:00",
                    "model": "test",
                    "prompt_version": "daily-note-v1",
                }
            )
        (self.root / "artifacts/public/data/daily_summaries.json").write_text(
            json.dumps(
                {
                    "schema_version": SUMMARY_SCHEMA,
                    "summaries": summaries,
                }
            ),
            encoding="utf-8",
        )

        sync_snapshot(self.root, self.archive)

        local = json.loads((self.archive / "data/daily_summaries.json").read_text())
        pairs = {(row["morning_report_id"], row["evening_report_id"]) for row in local["summaries"]}
        self.assertEqual(
            {
                ("2026-09-06-morning", "2026-09-05-evening"),
                ("2026-09-06-morning", "2026-09-06-evening"),
            },
            pairs,
        )

    def test_sync_rejects_archive_inside_public_repository(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the repository"):
            sync_snapshot(self.root, self.root / "archive")

    def test_sync_counts_a_report_date_even_before_its_morning_report_exists(self) -> None:
        index_path = self.root / "artifacts/public/data/reports.json"
        index = json.loads(index_path.read_text())
        index["reports"] = [row for row in index["reports"] if row["id"] != "2026-09-06-morning"]
        index_path.write_text(json.dumps(index), encoding="utf-8")
        (self.root / "artifacts/public/reports/2026-09-06-morning.md").unlink()

        sync_snapshot(self.root, self.archive)

        public = json.loads(index_path.read_text())
        public_ids = {row["id"] for row in public["reports"]}
        self.assertIn("2026-09-06-evening", public_ids)
        self.assertNotIn("2026-09-01-morning", public_ids)

    def test_build_site_copies_only_indexed_reports_and_markdown(self) -> None:
        sync_snapshot(self.root, self.archive)
        build_site(self.root, self.output, self.root / "artifacts/public/data/daily_summaries.json")

        report_data = json.loads((self.output / "data/reports.json").read_text())
        copied = {path.relative_to(self.output).as_posix() for path in (self.output / "reports").glob("*.md")}
        expected = {report["source_url"] for report in report_data["reports"]}
        self.assertEqual(expected, copied)
        self.assertEqual(10, len(report_data["reports"]))
        self.assertTrue((self.output / "legacy/summary-utils.js").is_file())
        self.assertTrue((self.output / "legacy/market-daily-utils.js").is_file())
        self.assertTrue((self.output / "legacy/report-markdown.js").is_file())
        self.assertEqual(
            "market_intel_pages.daily_summaries.v1",
            json.loads((self.output / "data/daily_summaries.json").read_text())["schema_version"],
        )

    def test_build_rejects_summary_with_unknown_source(self) -> None:
        (self.root / "artifacts/public/data/daily_summaries.json").write_text(
            json.dumps(
                {
                    "schema_version": SUMMARY_SCHEMA,
                    "summaries": [
                        {
                            "date": "2026-09-06",
                            "text": "sample",
                            "morning_report_id": "missing-morning",
                            "evening_report_id": "2026-09-06-evening",
                            "generated_at": "2026-09-07T07:00:00+08:00",
                            "model": "test",
                            "prompt_version": "daily-note-v1",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "source report"):
            build_site(self.root, self.output, self.root / "artifacts/public/data/daily_summaries.json")


if __name__ == "__main__":
    unittest.main()


def test_real_site_build_overlays_astro_pages_and_keeps_downloads(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "site"
    build_site(root, output)
    index_data = json.loads((output / "data/reports.json").read_text(encoding="utf-8"))
    report_id = index_data["reports"][0]["id"]
    index = (output / "index.html").read_text(encoding="utf-8")
    evening_dates = [row["date"] for row in index_data["reports"] if row["kind"] == "evening"]
    has_visual_history = bool(evening_dates) and any(
        "2026-09-25" <= day < max(evening_dates) for day in evening_dates
    )
    assert ('id="reports-title"' in index) is has_visual_history
    assert 'id="kind-filter"' not in index
    assert (output / f"reports/{report_id}/index.html").is_file()
    assert (output / "en/index.html").is_file()
    market = json.loads((output / "data/market_daily_report.json").read_text(encoding="utf-8"))
    market_date = market["run_id"].removeprefix("daily-")
    assert f"/quant-intel-platform/reports/{market_date}-market-daily-no-citations.md" in index
    assert (output / f"reports/{market_date}-market-daily.md").is_file()
    assert (output / f"reports/{market_date}-market-daily.txt").is_file()
    history = json.loads((output / "data/market_daily_reports.json").read_text(encoding="utf-8"))["reports"]
    for report in history:
        date = report["run_id"].removeprefix("daily-")
        reading = (output / f"reports/{date}-market-daily-no-citations.md").read_text(encoding="utf-8")
        assert f"# 美股市场日报（{date}）" in reading
        assert "https://" not in reading
        assert "证据：" not in reading
        if date != market_date:
            assert f"/quant-intel-platform/reports/{date}-market-daily-no-citations.md" not in index
    assert "| 5 年期 | 4.98% | -5.00 bp | 2026-09-25 |" in (
        output / "reports/2026-09-25-market-daily-no-citations.md"
    ).read_text(encoding="utf-8")
    sourced = (output / "reports/2026-09-25-market-daily.md").read_text(encoding="utf-8")
    plain = (output / "reports/2026-09-25-market-daily.txt").read_text(encoding="utf-8")
    assert sourced.index("## 美股市场表现") < sourced.index("## 主要个股") < sourced.index("## 美债收益率")
    assert sourced.index("## 美债收益率") < sourced.index("## 布伦特、金银与比特币")
    assert plain.index("一、美股市场表现") < plain.index("二、重点个股") < plain.index("三、美债收益率")
    assert plain.index("三、美债收益率") < plain.index("四、跨资产行情")


def test_refresh_astro_uses_latest_generated_snapshot(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "site"
    build_site(root, output)
    report_id = json.loads((output / "data/reports.json").read_text(encoding="utf-8"))["reports"][0]["id"]
    report = output / f"reports/{report_id}.md"
    report.write_text(report.read_text(encoding="utf-8") + "\n发布后解读标记\n", encoding="utf-8")
    refresh_astro(root, output)
    assert "发布后解读标记" in (output / f"reports/{report_id}/index.html").read_text(encoding="utf-8")


def test_reviewed_chart_renders_static_values_only_on_matching_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "site"
    build_site(root, output)
    reports = json.loads((output / "data/reports.json").read_text(encoding="utf-8"))["reports"]
    report_id = reports[0]["id"]
    other_id = reports[1]["id"]
    chart = output / f"data/charts/{report_id}.json"
    chart.parent.mkdir(parents=True, exist_ok=True)
    payload = public_chart()
    payload["report_id"] = report_id
    payload["date"] = reports[0]["date"]
    payload["kind"] = reports[0]["kind"]
    payload["charts"][0]["points"][0]["observation_date"] = reports[0]["date"]
    chart.write_text(json.dumps(rehash(payload), ensure_ascii=False), encoding="utf-8")
    refresh_astro(root, output)
    matching = (output / f"reports/{report_id}/index.html").read_text(encoding="utf-8")
    other = (output / f"reports/{other_id}/index.html").read_text(encoding="utf-8")
    self_contained = ("上涨家数", reports[0]["date"], "https://example.test/source")
    for text in self_contained:
        assert text in matching
    assert "astro-island" in matching
    assert "https://example.test/source" not in other
