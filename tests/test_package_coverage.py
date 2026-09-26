from __future__ import annotations

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


def test_package_minimums_cover_all_configured_production_sources() -> None:
    assert PACKAGE_MINIMUMS == {
        "a_share_analysis": 70.0,
        "a_share_daily": 65.0,
        "daily_messenger": 65.0,
        "ops_common": 50.0,
        "tushare_jobs": 35.0,
    }
