import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.generate_codex_commentary import run
from scripts.generate_daily_summary import current_summaries
from scripts.generate_daily_summary import run as run_summary
from scripts.generate_insights import _latest_insights
from scripts.generate_insights import run as run_insight
from tests.test_insights import analysis, sources


class CodexCommentaryTests(unittest.TestCase):
    def test_valid_codex_record_outweighs_later_cloud_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports.json"
            rows = sources()
            reports.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows})
            )
            codex = run_insight(
                reports,
                root / "codex.json",
                provider="codex",
                api_key="local",
                generator=lambda *_: analysis(),
            )["insights"][0]
            cloud = run_insight(
                reports,
                root / "cloud.json",
                provider="gemini",
                api_key="test",
                generator=lambda *_: analysis(),
            )["insights"][0]
            cloud["generated_at"] = "2026-09-30T23:00:00+08:00"
            self.assertEqual("codex", _latest_insights([codex, cloud], rows)[0]["provider"])

    def test_too_long_linked_overview_uses_independent_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, summaries, insights = (
                root / name for name in ("reports.json", "summaries.json", "insights.json")
            )
            reports.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": sources()})
            )
            summaries.write_text(json.dumps({"summaries": []}))
            run_summary(reports, summaries, summaries, "test", generator=lambda *_: "原有简评。")
            long_analysis = analysis()
            long_analysis["overview"]["text"] = "市场宽度仍待确认。" * 15
            run_insight(
                reports, insights, provider="gemini", api_key="test", generator=lambda *_: long_analysis
            )
            self.assertEqual(
                "generated summary",
                run_summary(
                    reports,
                    summaries,
                    summaries,
                    "test",
                    generator=lambda *_: "备用简评。",
                    insights_path=insights,
                    force=True,
                ),
            )
            self.assertEqual("备用简评。", json.loads(summaries.read_text())["summaries"][0]["text"])

    def test_cloud_insight_can_supply_summary_when_minimax_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, summaries, insights = (
                root / name for name in ("reports.json", "summaries.json", "insights.json")
            )
            reports.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": sources()})
            )
            summaries.write_text(json.dumps({"summaries": []}))
            run_insight(reports, insights, provider="gemini", api_key="test", generator=lambda *_: analysis())
            self.assertEqual(
                "generated summary",
                run_summary(reports, summaries, summaries, None, insights_path=insights),
            )
            self.assertEqual("gemini", json.loads(summaries.read_text())["summaries"][0]["provider"])

    def test_valid_cli_result_creates_both_indices_and_reuses_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, summaries, insights = (
                root / name for name in ("reports.json", "summaries.json", "insights.json")
            )
            reports.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": sources()})
            )

            def cli(arguments, **kwargs):
                self.assertIn("read-only", arguments)
                self.assertNotIn("GH_TOKEN", kwargs["env"])
                self.assertNotIn("GEMINI_API_KEY_2", kwargs["env"])
                Path(arguments[arguments.index("--output-last-message") + 1]).write_text(
                    json.dumps(analysis())
                )
                return SimpleNamespace(returncode=0)

            with (
                patch.dict(os.environ, {"GEMINI_API_KEY_2": "test-secret"}),
                patch("scripts.generate_codex_commentary.subprocess.run", side_effect=cli) as command,
            ):
                self.assertEqual(
                    "generated validated Codex commentary",
                    run(reports, summaries, insights, root / "archive", root / "work", Path("/bin/codex")),
                )
                self.assertEqual(
                    "reused validated Codex commentary",
                    run(reports, summaries, insights, root / "archive", root / "work", Path("/bin/codex")),
                )
            self.assertEqual(1, command.call_count)
            self.assertEqual("codex", json.loads(summaries.read_text())["summaries"][0]["provider"])
            self.assertEqual("codex", json.loads(insights.read_text())["insights"][0]["provider"])

            replacement = analysis()
            replacement["overview"]["text"] = "成交改善仍待确认。"
            run_insight(
                reports,
                insights,
                provider="gemini",
                api_key="test",
                force=True,
                generator=lambda *_: replacement,
            )
            self.assertEqual(
                "generated summary",
                run_summary(reports, summaries, summaries, None, insights_path=insights),
            )
            self.assertEqual("gemini", json.loads(summaries.read_text())["summaries"][0]["provider"])

    def test_summary_invalidates_when_historical_context_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = sources()
            older = json.loads(json.dumps(rows[0]))
            older["id"], older["date"] = "older", "2026-09-13"
            older["sections"][0]["paragraphs"][0] = "生成时间: 2026-09-13 19:00"
            rows.insert(0, older)
            reports, summaries, insights = (
                root / name for name in ("reports.json", "summaries.json", "insights.json")
            )
            reports.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows})
            )
            summaries.write_text(json.dumps({"summaries": []}))
            run_insight(reports, insights, provider="gemini", api_key="test", generator=lambda *_: analysis())
            run_summary(reports, summaries, summaries, None, insights_path=insights)
            self.assertEqual(1, len(current_summaries(rows, json.loads(summaries.read_text())["summaries"])))
            rows[0]["sections"][0]["paragraphs"].append("历史材料修订。")
            self.assertEqual(0, len(current_summaries(rows, json.loads(summaries.read_text())["summaries"])))

    def test_invalid_cli_analysis_does_not_write_indices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports, summaries, insights = (
                root / name for name in ("reports.json", "summaries.json", "insights.json")
            )
            reports.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": sources()})
            )

            def cli(arguments, **_):
                bad = analysis()
                bad["changes"][0]["text"] = "上涨率 99.9%。"
                Path(arguments[arguments.index("--output-last-message") + 1]).write_text(json.dumps(bad))
                return SimpleNamespace(returncode=0)

            with patch("scripts.generate_codex_commentary.subprocess.run", side_effect=cli):
                with self.assertRaises(ValueError):
                    run(reports, summaries, insights, root / "archive", root / "work", Path("/bin/codex"))
            self.assertFalse(summaries.exists())
            self.assertFalse(insights.exists())
