import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.generate_daily_summary import (
    generate_summary,
    run,
    select_source_pair,
    summary_source_hash,
    validate_summary,
)


def report(report_id, date, kind, generated_at):
    return {
        "id": report_id,
        "date": date,
        "kind": kind,
        "sections": [{"title": "metadata", "paragraphs": [f"生成时间: {generated_at}"]}],
    }


class SourcePairTests(unittest.TestCase):
    def test_pairs_latest_morning_with_preceding_evening(self):
        evening = report("2026-09-14-evening", "2026-09-14", "evening", "2026-09-14 19:08")
        morning = report("2026-09-14-morning", "2026-09-14", "morning", "2026-09-15 07:03")
        self.assertEqual((morning, evening), select_source_pair([evening, morning]))

    def test_uses_prior_evening_across_weekend(self):
        friday = report("fri", "2026-09-11", "evening", "2026-09-11 19:00")
        monday = report("mon", "2026-09-14", "morning", "2026-09-15 07:00")
        self.assertEqual((monday, friday), select_source_pair([friday, monday]))

    def test_excludes_evening_generated_after_morning(self):
        morning = report("m", "2026-09-14", "morning", "2026-09-15 07:00")
        later = report("e", "2026-09-14", "evening", "2026-09-15 19:00")
        self.assertIsNone(select_source_pair([morning, later]))

    def test_pairs_reports_generated_within_the_same_second(self):
        evening = report("e", "2026-09-18", "evening", "2026-09-19 15:00:00.100001")
        morning = report("m", "2026-09-18", "morning", "2026-09-19 15:00:00.100002")
        self.assertEqual((morning, evening), select_source_pair([evening, morning]))

    def test_requires_both_halves(self):
        morning = report("m", "2026-09-14", "morning", "2026-09-15 07:00")
        self.assertIsNone(select_source_pair([morning]))


class SummaryValidationTests(unittest.TestCase):
    def test_removes_think_block(self):
        self.assertEqual(
            "盘面偏弱，继续观察。", validate_summary("<think>hidden</think> 盘面偏弱，继续观察。")
        )

    def test_rejects_heading_list_empty_and_overlong_output(self):
        for value in ("# 今日", "- 条目", "", "盘" * 121):
            with self.subTest(value=value[:8]), self.assertRaises(ValueError):
                validate_summary(value)

    @patch("scripts.generate_daily_summary.urlopen")
    def test_uses_bearer_header_and_reads_chat_completion(self, open_url):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return '{"choices":[{"message":{"content":"盘面偏弱，继续观察。"}}]}'.encode()

        open_url.return_value = Response()
        result = generate_summary([], "secret-test-key", "test-model")
        request = open_url.call_args.args[0]
        self.assertEqual("盘面偏弱，继续观察。", result)
        self.assertEqual("Bearer secret-test-key", request.get_header("Authorization"))
        self.assertEqual(30, open_url.call_args.kwargs["timeout"])


class GenerationHistoryTests(unittest.TestCase):
    @patch("scripts.generate_daily_summary._load_published_history")
    def test_unpinned_remote_history_cannot_replace_verified_local_note(self, published):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rp, sp = root / "reports.json", root / "summaries.json"
            evening = report("e", "2026-09-14", "evening", "2026-09-14 19:00")
            morning = report("m", "2026-09-14", "morning", "2026-09-15 07:00")
            rp.write_text(json.dumps({"reports": [evening, morning]}))
            local = {
                "date": "2026-09-14",
                "text": "已校验内容",
                "morning_report_id": "m",
                "evening_report_id": "e",
                "source_hash": summary_source_hash(morning, evening),
            }
            sp.write_text(json.dumps({"summaries": [local]}))
            remote = {key: value for key, value in local.items() if key != "source_hash"}
            remote["text"] = "旧的未校验内容"
            published.return_value = [remote]
            run(rp, sp, sp, None, history_url="https://pages.invalid/history.json")
            self.assertEqual("已校验内容", json.loads(sp.read_text(encoding="utf-8"))["summaries"][0]["text"])

    @patch("scripts.generate_daily_summary.generate_summary", return_value="上涨率 56.3%。")
    def test_revised_source_removes_old_note_when_provider_is_unavailable(self, generate):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rp, sp = root / "reports.json", root / "summaries.json"
            rows = [
                report("e", "2026-09-14", "evening", "2026-09-14 19:00"),
                report("m", "2026-09-14", "morning", "2026-09-15 07:00"),
            ]
            rows[0]["sections"][0]["paragraphs"].append("上涨率 56.3%")
            rp.write_text(json.dumps({"reports": rows}))
            sp.write_text(json.dumps({"summaries": []}))
            run(rp, sp, sp, "key")
            rows[0]["sections"][0]["paragraphs"][-1] = "上涨率 30.0%"
            rp.write_text(json.dumps({"reports": rows}))
            run(rp, sp, sp, None)
            self.assertEqual([], json.loads(sp.read_text(encoding="utf-8"))["summaries"])

    @patch("scripts.generate_daily_summary.generate_summary", return_value="观察成交变化。")
    def test_source_revision_invalidates_cached_note(self, generate):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = [
                report("e", "2026-09-14", "evening", "2026-09-14 19:00"),
                report("m", "2026-09-14", "morning", "2026-09-15 07:00"),
            ]
            rp, sp = root / "reports.json", root / "summaries.json"
            rp.write_text(json.dumps({"reports": reports}))
            sp.write_text(json.dumps({"summaries": []}))
            run(rp, sp, sp, "key")
            reports[0]["sections"][0]["paragraphs"].append("上涨率 56.3%")
            rp.write_text(json.dumps({"reports": reports}))
            self.assertEqual("generated summary", run(rp, sp, sp, "key"))

    @patch("scripts.generate_daily_summary.generate_summary", return_value="观察成交变化。")
    def test_model_change_invalidates_cached_note(self, generate):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rp, sp = root / "reports.json", root / "summaries.json"
            rp.write_text(
                json.dumps(
                    {
                        "reports": [
                            report("e", "2026-09-14", "evening", "2026-09-14 19:00"),
                            report("m", "2026-09-14", "morning", "2026-09-15 07:00"),
                        ]
                    }
                )
            )
            sp.write_text(json.dumps({"summaries": []}))
            run(rp, sp, sp, "key", model="old")
            self.assertEqual("generated summary", run(rp, sp, sp, "key", model="new"))

    def test_missing_key_preserves_history_without_adding_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = [
                report("old-e", "2026-09-12", "evening", "2026-09-12 19:00"),
                report("old-m", "2026-09-13", "morning", "2026-09-14 07:00"),
                report("e", "2026-09-14", "evening", "2026-09-14 19:00"),
                report("m", "2026-09-14", "morning", "2026-09-15 07:00"),
            ]
            history = [
                {
                    "date": "2026-09-13",
                    "text": "existing",
                    "morning_report_id": "old-m",
                    "evening_report_id": "old-e",
                    "source_hash": summary_source_hash(reports[1], reports[0]),
                }
            ]
            (root / "reports.json").write_text(json.dumps({"reports": reports}))
            (root / "summaries.json").write_text(json.dumps({"summaries": history}))
            output = root / "out.json"
            status = run(root / "reports.json", root / "summaries.json", output, None)
            self.assertEqual("MiniMax key unavailable", status)
            self.assertEqual(history, json.loads(output.read_text())["summaries"])

    @patch("scripts.generate_daily_summary.generate_summary", return_value="新一日，先看成交能否跟上。")
    def test_success_adds_pair_at_most_once(self, generate):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = [
                report("e", "2026-09-14", "evening", "2026-09-14 19:00"),
                report("m", "2026-09-14", "morning", "2026-09-15 07:00"),
            ]
            (root / "reports.json").write_text(json.dumps({"reports": reports}))
            (root / "summaries.json").write_text(json.dumps({"summaries": []}))
            output = root / "out.json"
            self.assertEqual(
                "generated summary", run(root / "reports.json", root / "summaries.json", output, "key")
            )
            data = json.loads(output.read_text())["summaries"]
            self.assertEqual("m", data[0]["morning_report_id"])
            self.assertEqual("e", data[0]["evening_report_id"])
            self.assertEqual("reused existing summary", run(root / "reports.json", output, output, "key"))
            self.assertEqual(1, generate.call_count)

    @patch("scripts.generate_daily_summary.urlopen")
    def test_imports_previous_deployment_summaries(self, open_url):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps(
                    {
                        "schema_version": "market_intel_pages.daily_summaries.v1",
                        "summaries": [
                            {
                                "date": "2026-09-13",
                                "text": "previous",
                                "morning_report_id": "old-m",
                                "evening_report_id": "old-e",
                                "source_hash": summary_source_hash(
                                    report("old-m", "2026-09-13", "morning", "2026-09-14 07:00"),
                                    report("old-e", "2026-09-12", "evening", "2026-09-12 19:00"),
                                ),
                            }
                        ],
                    }
                ).encode()

        open_url.return_value = Response()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = [
                report("old-e", "2026-09-12", "evening", "2026-09-12 19:00"),
                report("old-m", "2026-09-13", "morning", "2026-09-14 07:00"),
                report("e", "2026-09-14", "evening", "2026-09-14 19:00"),
                report("m", "2026-09-14", "morning", "2026-09-15 07:00"),
            ]
            (root / "reports.json").write_text(json.dumps({"reports": reports}))
            (root / "summaries.json").write_text(json.dumps({"summaries": []}))
            output = root / "out.json"
            run(
                root / "reports.json",
                root / "summaries.json",
                output,
                None,
                history_url="https://pages.invalid/data/daily_summaries.json",
            )
            self.assertEqual("previous", json.loads(output.read_text())["summaries"][0]["text"])


if __name__ == "__main__":
    unittest.main()
