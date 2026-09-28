import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pytest

from scripts.import_reports import import_reports
from scripts.pipeline_health import health_report


class PipelineTests(unittest.TestCase):
    def test_correction_to_expired_public_report_preserves_archived_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            root, source, archive = p / "site", p / "source", p / "archive"
            (root / "artifacts/public/data").mkdir(parents=True)
            (root / "artifacts/public/reports").mkdir()
            source.mkdir()
            (root / "artifacts/public/data/reports.json").write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": []})
            )
            (root / "artifacts/public/data/daily_summaries.json").write_text(
                json.dumps({"schema_version": "market_intel_pages.daily_summaries.v1", "summaries": []})
            )
            entries = []
            for day in range(1, 7):
                date = f"2026-09-{day:02d}"
                (source / f"{day}.md").write_text(
                    f"# 收盘\n生成时间: {date} 19:00\n## 盘面\n原始版本。\n", encoding="utf-8"
                )
                entries.append({"path": f"{day}.md", "date": date, "kind": "evening"})
            manifest = source / "public.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "market_intel_pages.import.v1",
                        "publication": "public",
                        "reports": entries,
                    }
                )
            )
            import_reports(root, manifest, archive, apply=True)
            self.assertFalse((root / "artifacts/public/reports/2026-09-01-evening.md").exists())
            (source / "1.md").write_text(
                "# 收盘\n生成时间: 2026-09-01 19:00\n## 盘面\n更正版本。\n", encoding="utf-8"
            )
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "market_intel_pages.import.v1",
                        "publication": "public",
                        "reports": entries[:1],
                    }
                )
            )
            import_reports(root, manifest, archive, apply=True)
            revisions = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in (archive / "report_revisions").glob("*.json")
            ]
            originals = [
                r
                for r in revisions
                if r["report"]["id"] == "2026-09-01-evening" and "原始版本" in r["markdown"]
            ]
            self.assertTrue(originals)

    def test_health_uses_source_time_not_recent_build_time(self):
        data = {
            "generated_at": "2026-09-19T08:00:00+08:00",
            "reports": [
                {
                    "id": "e",
                    "kind": "evening",
                    "date": "2026-09-14",
                    "sections": [{"title": "meta", "paragraphs": ["生成时间: 2026-09-14 19:00"]}],
                }
            ],
        }
        status = health_report(data, now=datetime.fromisoformat("2026-09-19T09:00:00+08:00"))
        self.assertEqual("stale", status["status"])
        self.assertEqual(110, status["source_age_hours"])
        self.assertIsNone(status["expected_date"])

    def test_health_can_follow_supplied_exchange_calendar_target(self):
        data = {
            "reports": [
                {
                    "id": "e",
                    "kind": "evening",
                    "date": "2026-09-18",
                    "sections": [{"paragraphs": ["生成时间: 2026-09-18 19:00"]}],
                }
            ]
        }
        status = health_report(
            data, expected_date="2026-09-18", now=datetime.fromisoformat("2026-09-21T07:00:00+08:00")
        )
        self.assertEqual("current", status["status"])

    def test_import_is_idempotent_and_archives_before_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            root, source, archive = p / "site", p / "source", p / "archive"
            (root / "artifacts/public/data").mkdir(parents=True)
            (root / "artifacts/public/reports").mkdir()
            source.mkdir()
            (root / "artifacts/public/data/reports.json").write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": []})
            )
            (root / "artifacts/public/data/daily_summaries.json").write_text(
                json.dumps({"schema_version": "market_intel_pages.daily_summaries.v1", "summaries": []})
            )
            (source / "report.md").write_text(
                "# 收盘复盘\n\n生成时间: 2026-09-18 19:00\n\n## 市场\n上涨率 56.3%。\n", encoding="utf-8"
            )
            manifest = source / "public.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "market_intel_pages.import.v1",
                        "publication": "public",
                        "reports": [{"path": "report.md", "date": "2026-09-18", "kind": "evening"}],
                    }
                )
            )
            result = import_reports(root, manifest, archive, apply=False)
            self.assertEqual(1, result["changed"])
            self.assertEqual(
                [], json.loads((root / "artifacts/public/data/reports.json").read_text())["reports"]
            )
            import_reports(root, manifest, archive, apply=True)
            self.assertTrue((root / "artifacts/public/data/reports.json").is_file())
            self.assertTrue((archive / "reports/2026-09-18-evening.md").exists())
            before = (root / "artifacts/public/data/reports.json").read_bytes()
            self.assertEqual(0, import_reports(root, manifest, archive, apply=True)["changed"])
            self.assertEqual(before, (root / "artifacts/public/data/reports.json").read_bytes())

    def test_import_rejects_unsafe_source_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            manifest = p / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "market_intel_pages.import.v1",
                        "publication": "public",
                        "reports": [{"path": "../private.md", "date": "2026-09-18", "kind": "evening"}],
                    }
                )
            )
            with self.assertRaises(ValueError):
                import_reports(p / "repo", manifest, p / "archive", apply=True)
            self.assertFalse((p / "repo").exists())


if __name__ == "__main__":
    unittest.main()


def test_public_report_path_rejects_traversal_before_reading(tmp_path):
    from scripts.public_paths import safe_public_report_path

    with pytest.raises(ValueError):
        safe_public_report_path(tmp_path, "reports/../secret.md")
