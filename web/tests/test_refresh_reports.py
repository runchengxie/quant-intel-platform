import importlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

OWNER = r"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(__file__).parent
settings = json.loads((root / "settings.json").read_text())
time.sleep(settings.get("delay", 0))
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    keys = ("DATA_PLATFORM_ROOT", "A_SHARE_OUTPUT_DIR", "CROSS_MARKET_SNAPSHOT_ROOT",
            "MARKET_INTEL_REPORT_AUDIT_ONLY")
    log.write(json.dumps({"args": args, "env": {key: os.environ.get(key) for key in keys}}) + "\n")
print("private diagnostic marker", file=sys.stderr)
if settings.get("fail_on") == args[0]:
    raise SystemExit(9)
if args[0] == "evening":
    date = args[args.index("--date") + 1]
    if "--json" in args:
        result = {
            "trade_date": date,
            "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "overview": {"breadth": {"total": 5000}, "turnover_total": 2000000},
        }
        result.update(settings.get("evening", {}))
        print(json.dumps(result))
    else:
        print(settings.get("markdown", f"## {date} 盘后点评\n\n## 市场\n上涨 3000 家。"))
elif args[0] == "morning":
    date = args[args.index("--date") + 1]
    result = {"pipeline": "morning", "report_kind": "morning", "date": date,
              "date_dash": "2026-09-18", "cross_market": {"date": date, "_source": "data-snapshots"}}
    result.update(settings.get("morning", {}))
    print(json.dumps(result))
elif args[0] == "morning-report":
    news = json.loads(Path(args[args.index("--news") + 1]).read_text())
    if news != {"markets": {}, "markets_requested": [], "disabled": True}:
        raise SystemExit(8)
    text = "# 亚洲市场盘前（2026-09-18）\n\n生成时间: 2026-09-19 15:11\n\n## 市场\nSPY +1.13%。"
    Path(args[args.index("--out") + 1]).write_text(text)
    print(text)
else:
    raise SystemExit(7)
"""


class RefreshReportsTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("scripts.refresh_reports")
        self.refresh = self.module.refresh_reports
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.owner = self.base / "owner-cli"
        self.owner.write_text(f"#!{sys.executable}\n" + OWNER, encoding="utf-8")
        self.owner.chmod(0o700)
        self.data, self.snapshots, self.output = [self.base / name for name in ("data", "snapshots", "out")]
        self.data.mkdir()
        (self.snapshots / "cross-market").mkdir(parents=True)
        self.snapshot = self.snapshots / "cross-market/2026-09-18.json"
        self.snapshot.write_text('{"date": "20260918"}', encoding="utf-8")
        self.settings()

    def settings(self, **values):
        (self.base / "settings.json").write_text(json.dumps(values), encoding="utf-8")

    def run_refresh(self, kind="evening", **options):
        return self.refresh(self.owner, self.data, self.snapshots, self.output, "2026-09-18", kind, **options)

    def cli_args(self):
        return [
            "refresh_reports.py",
            "--owner-cli",
            str(self.owner),
            "--data-root",
            str(self.data),
            "--snapshot-root",
            str(self.snapshots),
            "--output-dir",
            str(self.output),
            "--date",
            "2026-09-18",
            "--kind",
            "both",
            "--generation-mode",
            "scheduled",
            "--timeout-seconds",
            "180",
        ]

    def public_files(self):
        return {
            path.relative_to(self.output): path.read_bytes() for path in self.output.glob("public/**/*.md")
        }

    def assert_last_good(self, manifest, markdown):
        self.assertEqual(manifest, (self.output / "manifest.json").read_bytes())
        self.assertEqual(markdown, self.public_files())

    def test_both_kinds_publish_importable_backfills_without_delivery_or_private_artifacts(self):
        manifest_path = self.run_refresh("both")
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual("market_intel_pages.import.v1", manifest["schema_version"])
        self.assertEqual("public", manifest["publication"])
        self.assertEqual({"morning", "evening"}, {row["kind"] for row in manifest["reports"]})
        for row in manifest["reports"]:
            self.assertEqual("2026-09-18", row["date"])
            self.assertTrue(row["path"].startswith("public/"))
            text = (self.output / row["path"]).read_text()
            self.assertIn("数据日期: 2026-09-18", text)
            self.assertIn("报告生成方式: backfill", text)
            self.assertIn("补发", text)
            self.assertNotIn("private diagnostic marker", text)
            generated = next(
                line.removeprefix("生成时间: ") for line in text.splitlines() if line.startswith("生成时间: ")
            )
            timestamp = datetime.strptime(generated, "%Y-%m-%d %H:%M:%S.%f")
            now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
            self.assertLess(abs((now - timestamp).total_seconds()), 15)
        old_markdown = self.public_files()
        with patch.object(sys, "argv", self.cli_args()), redirect_stdout(io.StringIO()) as stdout:
            self.module.main()
        result = json.loads(stdout.getvalue())
        self.assertEqual({"manifest": str(manifest_path), "errors": []}, result)
        for row in json.loads(manifest_path.read_text())["reports"]:
            self.assertIn("报告生成方式: scheduled", (self.output / row["path"]).read_text())
        for path, contents in old_markdown.items():
            self.assertEqual(contents, (self.output / path).read_bytes())
        calls = [json.loads(line) for line in (self.base / "calls.jsonl").read_text().splitlines()]
        self.assertEqual(
            ["evening", "evening", "morning", "morning-report"] * 2, [call["args"][0] for call in calls]
        )
        for call in calls:
            self.assertNotIn("--send-feishu", call["args"])
            self.assertEqual("1", call["env"]["MARKET_INTEL_REPORT_AUDIT_ONLY"])
            self.assertEqual(str(self.data), call["env"]["DATA_PLATFORM_ROOT"])
            self.assertEqual(str(self.snapshots), call["env"]["CROSS_MARKET_SNAPSHOT_ROOT"])
            self.assertTrue(Path(call["env"]["A_SHARE_OUTPUT_DIR"]).is_relative_to(self.output))
        self.assertTrue(list(self.output.glob(".private-batches/**/*.stderr.log")))

    def test_public_timestamps_preserve_actual_microseconds_within_one_second(self):
        earlier = datetime(2026, 9, 19, 15, 30, 0, 123456, tzinfo=timezone(timedelta(hours=8)))
        later = earlier.replace(microsecond=234567)
        with patch.object(self.module, "datetime") as clock:
            clock.now.side_effect = [earlier, later]
            evening = self.module.public_markdown("## 20260918 盘后点评", "2026-09-18", "evening", "backfill")
            morning = self.module.public_markdown("# 盘前（2026-09-18）", "2026-09-18", "morning", "backfill")
        self.assertIn("生成时间: 2026-09-19 15:30:00.123456", evening)
        self.assertIn("生成时间: 2026-09-19 15:30:00.234567", morning)

    def test_output_rejects_private_and_public_symlinks_before_running_owner(self):
        cases = [(".private-batches", False), (".private-batches", True), ("public", False), ("public", True)]
        for index, (name, dangling) in enumerate(cases):
            with self.subTest(name=name, dangling=dangling):
                foreign = self.base / f"foreign-repo-{index}"
                (foreign / ".git").mkdir(parents=True)
                self.output = self.base / f"out-{index}"
                self.output.mkdir()
                calls = self.base / "calls.jsonl"
                calls.unlink(missing_ok=True)
                target = self.base / f"missing-target-{index}" if dangling else foreign
                (self.output / name).symlink_to(target, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "output"):
                    self.run_refresh()
                self.assertFalse(calls.exists())
                self.assertEqual([".git"], sorted(path.name for path in foreign.iterdir()))
                self.assertFalse((self.output / "manifest.json").exists())

    def test_failed_second_kind_preserves_last_good_manifest_and_markdown(self):
        manifest = self.run_refresh().read_bytes()
        markdown = self.public_files()
        self.settings(fail_on="morning-report")
        with self.assertRaisesRegex(ValueError, "owner CLI") as caught:
            self.run_refresh("both")
        self.assertNotIn("private diagnostic marker", str(caught.exception))
        self.assert_last_good(manifest, markdown)
        with patch.object(sys, "argv", self.cli_args()), redirect_stdout(io.StringIO()) as stdout:
            with self.assertRaises(SystemExit) as exited:
                self.module.main()
        self.assertEqual(1, exited.exception.code)
        result = json.loads(stdout.getvalue())
        self.assertIsNone(result["manifest"])
        self.assertTrue(result["errors"])
        self.assertNotIn("private diagnostic marker", stdout.getvalue())
        self.settings(delay=0.1)
        with self.assertRaisesRegex(ValueError, "timeout"):
            self.run_refresh(timeout_seconds=0.01)
        self.assert_last_good(manifest, markdown)

    def test_evening_rejects_wrong_identity_empty_data_and_private_text_before_publication(self):
        manifest = self.run_refresh().read_bytes()
        markdown = self.public_files()
        cases = [
            {"evening": {"trade_date": "20260917"}},
            {"evening": {"generated_at": "invalid"}},
            {"evening": {"generated_at": "2026-09-18T12:00:00"}},
            {"evening": {"overview": {"breadth": {"total": 0}, "turnover_total": 0}}},
            {"markdown": "## 20260917 盘后点评\n市场事实。"},
            {"markdown": "## 20260918 盘后点评\n/home/private/secret.json"},
            {"markdown": "## 20260918 盘后点评\noc_1234567890abcdef"},
            {"markdown": "## 20260918 盘后点评\napi_key=credential-value"},
        ]
        for case in cases:
            with self.subTest(case=case):
                self.settings(**case)
                with self.assertRaises(ValueError):
                    self.run_refresh()
                self.assert_last_good(manifest, markdown)

    def test_morning_preflight_blocks_missing_snapshot_and_owner_stray_cleanup(self):
        self.snapshot.unlink()
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.run_refresh("morning")
        self.snapshot.write_text('{"date": "20260917"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.run_refresh("morning")
        self.snapshot.write_text('{"date": "20260918"}', encoding="utf-8")
        stray = self.data / "assets/tushare/a_share/ths_hot/data"
        stray.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "owner"):
            self.run_refresh("morning")
        self.assertTrue(stray.is_dir())
        self.assertFalse((self.base / "calls.jsonl").exists())
        self.assertFalse((self.output / "manifest.json").exists())
        self.output.mkdir()
        (self.output / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside Git"):
            self.run_refresh()
        (self.output / ".git").rmdir()
        (self.base / ".git").mkdir()
        with patch.object(self.module, "__file__", str(self.base / "repo/scripts/refresh_reports.py")):
            self.assertTrue(self.run_refresh().is_file())

    def test_morning_rejects_live_fallback_or_mismatched_dates(self):
        manifest = self.run_refresh().read_bytes()
        markdown = self.public_files()
        for change in [
            {"date": "20260917"},
            {"date_dash": "2026-09-17"},
            {"cross_market": {"date": "20260918", "_source": "live"}},
            {"cross_market": {"date": "20260917", "_source": "data-snapshots"}},
        ]:
            with self.subTest(change=change):
                self.settings(morning=change)
                with self.assertRaises(ValueError):
                    self.run_refresh("morning")
                self.assert_last_good(manifest, markdown)


if __name__ == "__main__":
    unittest.main()
