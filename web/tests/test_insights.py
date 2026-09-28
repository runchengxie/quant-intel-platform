import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.generate_insights import _valid_history, run
from scripts.insight_contract import build_context, evaluate_watchpoints, source_hash, validate_analysis


def sources():
    return [
        {
            "id": "e1",
            "date": "2026-09-14",
            "kind": "evening",
            "title": "复盘",
            "sections": [
                {
                    "title": "盘面",
                    "paragraphs": [
                        "生成时间: 2026-09-14 19:00",
                        "上涨率 56.3%；成交额/历史中位 0.82x。",
                        "[WARN] 新闻条目缺失。",
                    ],
                }
            ],
        },
        {
            "id": "m1",
            "date": "2026-09-14",
            "kind": "morning",
            "title": "晨报",
            "sections": [
                {"title": "隔夜", "paragraphs": ["生成时间: 2026-09-15 07:00", "SMH -4.75%，QQQ -0.80%。"]}
            ],
        },
    ]


def analysis():
    return {
        "overview": {"text": "个股修复还需要成交确认。", "evidence_ids": ["e1:s0:p1"]},
        "changes": [{"text": "上涨率 56.3%。", "evidence_ids": ["e1:s0:p1"]}],
        "tensions": [{"text": "半导体走弱。", "evidence_ids": ["m1:s0:p1"]}],
        "watchpoints": [
            {
                "question": "成交能否改善？",
                "metric": "volume_ratio",
                "operator": ">",
                "threshold": 0.82,
                "evidence_ids": ["e1:s0:p1"],
            }
        ],
    }


class InsightContractTests(unittest.TestCase):
    def test_unused_context_eviction_does_not_drop_yesterdays_note(self):
        rows = sources()
        old = copy.deepcopy(rows[0])
        old.update(id="old", date="2026-09-10")
        old["sections"][0]["paragraphs"][0] = "生成时间: 2026-09-10 19:00"
        context = build_context([old] + rows, rows[1], rows[0])
        note = {**context, "id": "saved", "analysis": analysis()}
        retained = _valid_history([note], rows)
        self.assertEqual(1, len(retained))
        self.assertNotIn("old", retained[0]["source_report_ids"])
        self.assertFalse(any(e["report_id"] == "old" for e in retained[0]["evidence"]))

    def test_content_revision_changes_identity(self):
        rows = sources()
        before = source_hash(rows)
        rows[0]["sections"][0]["paragraphs"][1] = "上涨率 40.0%"
        self.assertNotEqual(before, source_hash(rows))

    def test_context_excludes_reports_after_cutoff(self):
        rows = sources()
        future = copy.deepcopy(rows[0])
        future.update(id="future", date="2026-09-15")
        future["sections"][0]["paragraphs"][0] = "生成时间: 2026-09-15 19:00"
        context = build_context(rows + [future], rows[1], rows[0])
        self.assertNotIn("future", {e["report_id"] for e in context["evidence"]})
        self.assertEqual(0.82, context["metrics"]["volume_ratio"]["value"])
        self.assertTrue(context["quality_warnings"])

    def test_rejects_fabricated_citation_and_unbacked_number(self):
        rows = sources()
        context = build_context(rows, rows[1], rows[0])
        for field, value in [("evidence_ids", ["unknown"]), ("text", "上涨率 99.9%")]:
            bad = analysis()
            bad["changes"][0][field] = value
            with self.assertRaises(ValueError):
                validate_analysis(bad, context)
        self.assertEqual(analysis(), validate_analysis(analysis(), context))

    def test_rejects_invented_threshold(self):
        rows = sources()
        bad = analysis()
        bad["watchpoints"][0]["threshold"] = 1.5
        with self.assertRaises(ValueError):
            validate_analysis(bad, build_context(rows, rows[1], rows[0]))

    def test_verification_uses_first_later_evening_and_preserves_original(self):
        rows = sources()
        note = {
            "id": "note1",
            "date": "2026-09-14",
            "as_of": "2026-09-15T07:00:00+08:00",
            "analysis": analysis(),
        }
        original = copy.deepcopy(note)
        later = copy.deepcopy(rows[0])
        later.update(id="e2", date="2026-09-15")
        later["sections"][0]["paragraphs"] = ["生成时间: 2026-09-15 19:00", "成交额/历史中位 0.90x"]
        results = evaluate_watchpoints([note], rows + [later])
        self.assertEqual("met", results[0]["status"])
        self.assertEqual(0.9, results[0]["observed_value"])
        self.assertEqual("e2", results[0]["report_id"])
        self.assertEqual(original, note)

    def test_missing_metric_remains_unverifiable(self):
        rows = sources()
        later = copy.deepcopy(rows[0])
        later.update(id="e2", date="2026-09-15")
        later["sections"][0]["paragraphs"] = ["生成时间: 2026-09-15 19:00", "成交数据缺失"]
        note = {
            "id": "note1",
            "date": "2026-09-14",
            "as_of": "2026-09-15T07:00:00+08:00",
            "analysis": analysis(),
        }
        self.assertEqual("unverifiable", evaluate_watchpoints([note], rows + [later])[0]["status"])


class GenerationTests(unittest.TestCase):
    def test_http_failure_publishes_safe_status_without_exception_text(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            rp = p / "reports.json"
            rp.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": sources()})
            )

            def denied(*args):
                error = HTTPError("", 403, "private response", {}, None)
                error.diagnostics = {"http_status": 403, "api_status": "PERMISSION_DENIED"}
                raise error

            result = run(rp, p / "insights.json", api_key="secret", generator=denied)
            self.assertEqual(403, result["generation"]["diagnostics"]["http_status"])
            self.assertNotIn("private response", json.dumps(result))
            self.assertNotIn("secret", json.dumps(result))

    def test_replacement_keeps_verifying_the_original_archived_condition(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            rp, ip = p / "reports.json", p / "insights.json"
            rows = sources()
            rp.write_text(json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows}))
            first = run(rp, ip, api_key="test", archive_dir=p / "archive", generator=lambda *args: analysis())
            old_id = first["insights"][0]["id"]
            replacement = analysis()
            replacement["watchpoints"][0]["operator"] = "<"
            run(
                rp,
                ip,
                api_key="test",
                archive_dir=p / "archive",
                force=True,
                generator=lambda *args: replacement,
            )
            later = copy.deepcopy(rows[0])
            later.update(id="e2", date="2026-09-15")
            later["sections"][0]["paragraphs"] = ["生成时间: 2026-09-15 19:00", "成交额/历史中位 0.90x"]
            rp.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows + [later]})
            )
            run(rp, ip, api_key=None, archive_dir=p / "archive")
            outcomes = [
                json.loads(f.read_text(encoding="utf-8")) for f in (p / "archive/outcomes").glob("*.json")
            ]
            self.assertTrue(any(o["insight_id"] == old_id and o["status"] == "met" for o in outcomes))

    def test_same_day_evening_replay_is_not_labelled_daily(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            rp = p / "reports.json"
            rp.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": sources()})
            )
            with patch("scripts.generate_insights.datetime", wraps=datetime) as clock:
                clock.now.return_value = datetime.fromisoformat("2026-09-15T19:30:00+08:00")
                result = run(rp, p / "insights.json", api_key="test", generator=lambda *args: analysis())
            self.assertEqual("retrospective", result["insights"][0]["generation_mode"])

    def test_generation_cache_revision_and_append_only_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            rp, ip = p / "reports.json", p / "insights.json"
            rows = sources()
            rp.write_text(json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows}))
            args = {
                "provider": "gemini",
                "model": "test",
                "api_key": "test",
                "archive_dir": p / "archive",
                "generator": lambda *args: analysis(),
            }
            first = run(rp, ip, **args)
            self.assertEqual("generated", first["generation"]["status"])
            second = run(rp, ip, **args)
            self.assertEqual("cached", second["generation"]["status"])
            stale_fingerprint = json.loads(ip.read_text())
            stale_fingerprint["insights"][0]["fingerprint"] = "old-prompt"
            ip.write_text(json.dumps(stale_fingerprint))
            revised_prompt = run(rp, ip, **args)
            self.assertEqual("generated", revised_prompt["generation"]["status"])
            rows[1]["sections"][0]["paragraphs"].append("背景更新。")
            rp.write_text(json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows}))
            third = run(rp, ip, **args)
            self.assertEqual("generated", third["generation"]["status"])
            self.assertEqual(3, len(list((p / "archive/insights").glob("*.json"))))
            self.assertNotEqual(first["insights"][0]["id"], third["insights"][0]["id"])

    def test_missing_credentials_publish_explicit_state(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            rp = p / "reports.json"
            rp.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": sources()})
            )
            result = run(rp, p / "insights.json", api_key=None)
            self.assertEqual("not_configured", result["generation"]["status"])
            self.assertEqual([], result["insights"])

    def test_provider_failure_does_not_publish_stale_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            rp, ip = p / "reports.json", p / "insights.json"
            rows = sources()
            rp.write_text(json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows}))
            run(rp, ip, api_key="test", generator=lambda *args: analysis())
            rows[1]["sections"][0]["paragraphs"].append("修订。")
            rp.write_text(json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": rows}))

            def fail(*args):
                raise TimeoutError("provider failed")

            result = run(rp, ip, api_key="test", generator=fail)
            self.assertEqual("unavailable", result["generation"]["status"])
            self.assertEqual([], result["insights"])

    def test_validation_failure_reports_fixed_code_without_model_text(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            rp, ip = p / "reports.json", p / "insights.json"
            rp.write_text(
                json.dumps({"schema_version": "market_intel_pages.reports.v1", "reports": sources()})
            )

            def invalid(*args):
                raise ValueError("number not supported by cited evidence: secret model prose")

            result = run(rp, ip, api_key="test", generator=invalid)
            generation = result["generation"]
            self.assertEqual("analysis_validation_failed", generation["error_code"])
            self.assertNotIn("secret model prose", json.dumps(generation))
            self.assertEqual(1, generation["analysis_attempts"])


if __name__ == "__main__":
    unittest.main()
