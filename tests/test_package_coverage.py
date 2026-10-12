from __future__ import annotations

import json
import runpy
from pathlib import Path

from coverage import Coverage

from project_tools import package_coverage
from project_tools.package_coverage import (
    PACKAGE_MINIMUMS,
    package_coverage_percentages,
    package_threshold_violations,
)


def test_package_coverage_aggregates_statement_counts_per_source_package() -> None:
    report_files = {
        "src/a_share_daily/first.py": {"summary": {"covered_lines": 8, "num_statements": 10}},
        "src/a_share_daily/nested/second.py": {
            "summary": {"covered_lines": 3, "num_statements": 5}
        },
        "tests/a_share_daily/test_first.py": {
            "summary": {"covered_lines": 100, "num_statements": 100}
        },
    }

    assert package_coverage_percentages(report_files) == {"a_share_daily": 11 / 15 * 100}


def test_package_thresholds_fail_for_low_and_missing_packages() -> None:
    thresholds = {"a_share_daily": 65.0, "ops_common": 50.0}
    violations = package_threshold_violations(
        {"a_share_daily": 64.9},
        thresholds=thresholds,
    )

    assert violations == [
        "a_share_daily: 64.9% is below the 65.0% minimum",
        "ops_common: no source files were measured",
    ]


def test_existing_package_floors_are_preserved() -> None:
    for package, minimum in {
        "a_share_analysis": 70.0,
        "a_share_daily": 65.0,
        "daily_messenger": 65.0,
        "ops_common": 50.0,
        "tushare_jobs": 35.0,
    }.items():
        assert package_threshold_violations(
            {package: minimum - 0.1}, thresholds={package: PACKAGE_MINIMUMS[package]}
        )
        assert not package_threshold_violations(
            {package: minimum}, thresholds={package: PACKAGE_MINIMUMS[package]}
        )


def test_unimported_production_modules_are_present_in_real_coverage(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    coverage = Coverage(config_file=str(root / "pyproject.toml"), data_file=str(tmp_path / "data"))
    coverage.start()
    try:
        runpy.run_path(str(root / "src/tushare_jobs/constants.py"))
    finally:
        coverage.stop()
    report = tmp_path / "report.json"
    coverage.json_report(outfile=str(report))
    files = json.loads(report.read_text(encoding="utf-8"))["files"]
    for filename in (
        "src/market_intel_publication/import_reports.py",
        "src/market_intel_commentary/generate_commentary.py",
        "src/market_intel_config/audiences.py",
        "src/research_contracts/file_receipts.py",
        "src/style_replica_bridge/tearsheet.py",
    ):
        assert filename in files


def test_new_production_packages_cannot_be_omitted_from_the_gate() -> None:
    old_packages = {
        "a_share_analysis": 100.0,
        "a_share_daily": 100.0,
        "daily_messenger": 100.0,
        "ops_common": 100.0,
        "tushare_jobs": 100.0,
    }
    violations = package_threshold_violations(old_packages)
    assert violations == [
        "market_intel_commentary: no source files were measured",
        "market_intel_config: no source files were measured",
        "market_intel_publication: no source files were measured",
        "research_contracts: no source files were measured",
        "style_replica_bridge: no source files were measured",
    ]


def test_package_gate_loads_coverage_from_selected_external_file(tmp_path, monkeypatch) -> None:
    root = tmp_path / "project"
    source = root / "src/example"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    module = source / "operation.py"
    module.write_text("answer = 42\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[tool.coverage.run]\nsource = ["src"]\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)
    monkeypatch.setattr(package_coverage, "ROOT", root)
    data_file = tmp_path / "outside.coverage"
    monkeypatch.setenv("COVERAGE_FILE", str(data_file))
    coverage = Coverage(config_file=str(root / "pyproject.toml"), data_file=str(data_file))
    coverage.start()
    try:
        runpy.run_path(str(module))
    finally:
        coverage.stop()
    coverage.save()

    assert not (root / ".coverage").exists()
    files = package_coverage._coverage_report_files()
    assert files["src/example/operation.py"]["summary"]["covered_lines"] == 1


def test_scope_gate_rejects_unmeasured_files_and_packages_without_a_floor(tmp_path, monkeypatch):
    root = tmp_path / "project"
    for filename in ("src/ops_common/first.py", "src/ops_common/new.py", "src/new_package/run.py"):
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(package_coverage, "ROOT", root)
    files = {"src/ops_common/first.py": {"summary": {"covered_lines": 1, "num_statements": 1}}}
    assert package_coverage.coverage_scope_violations(files) == [
        "new_package: no package coverage minimum is configured",
        "src/new_package/run.py: source file was not measured",
        "src/ops_common/new.py: source file was not measured",
    ]
