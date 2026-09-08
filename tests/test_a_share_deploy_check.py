from __future__ import annotations

import json
from pathlib import Path

from a_share_daily.deploy_check import (
    REPORT_DATASETS,
    REPORT_DATASETS_OPTIONAL,
    REPORT_DATASETS_REQUIRED,
    SCRIPT_NAMES,
    _check_minute_campaign,
    _check_report_artifact_health,
    _check_tushare_credentials,
    _check_watchdog_alert_env,
    _runtime_project_root,
    exit_code,
    format_results,
    run_checks,
)
from a_share_daily.deploy_check.env_helpers import _api_key_flags


def test_report_artifact_health_detects_missing_chart_file_and_failed_delivery(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    manifest = output_dir / "morning_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "date": "20260831",
                "charts": {
                    "ok": ["dashboard"],
                    "failed": [],
                    "skipped": [],
                    "degraded": [],
                    "errors": {},
                    "paths": {"dashboard": str(output_dir / "missing.png")},
                },
            }
        ),
        encoding="utf-8",
    )
    delivery_dir = tmp_path / "state" / "a_share_daily_delivery"
    delivery_dir.mkdir(parents=True)
    (delivery_dir / "morning_latest.json").write_text(
        json.dumps({"success": False, "trade_date": "20260831"}), encoding="utf-8"
    )

    result = _check_report_artifact_health(
        tmp_path,
        {
            "A_SHARE_OUTPUT_DIR": str(output_dir),
            "A_SHARE_DELIVERY_STATE_DIR": str(delivery_dir),
        },
    )

    assert result.status == "warn"
    assert "missing_files" in result.detail
    assert "delivery_failed" in result.detail


def test_watchdog_alert_target_accepts_supervisor_fallback() -> None:
    result = _check_watchdog_alert_env({"A_SHARE_FEISHU_DM_CHAT_ID": "oc_personal"})
    assert result.name == "watchdog alert target"
    assert result.status == "ok", result.detail


def test_watchdog_alert_target_warns_when_unconfigured() -> None:
    result = _check_watchdog_alert_env({})
    assert result.name == "watchdog alert target"
    assert result.status == "warn"
    assert "WATCHDOG_ALERT_FEISHU_CHAT_ID" in result.detail


def test_minute_campaign_check_reports_stalled_ledger(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    campaign = data_root / "metadata/minute_backfill/tushare_historical_campaign_v1_20260831"
    campaign.mkdir(parents=True)
    (campaign / "ledger.json").write_text(
        json.dumps(
            {
                "health": {
                    "state": "stalled",
                    "last_reason": "retryable_lane_error",
                    "no_progress_streak": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    result = _check_minute_campaign({"DATA_PLATFORM_ROOT": str(data_root)})

    assert result.status == "warn"
    assert "stalled" in result.detail
    assert "retryable_lane_error" in result.detail


def test_minute_campaign_check_is_quiet_when_not_configured(tmp_path: Path) -> None:
    result = _check_minute_campaign({"DATA_PLATFORM_ROOT": str(tmp_path / "data")})

    assert result.status == "ok"
    assert "未发现" in result.detail


def test_report_artifact_health_detects_evening_manifest_kind_mismatch(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    manifest = output_dir / "evening_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "pipeline": "morning",
                "date": "20260831",
                "charts": {"paths": {}},
            }
        ),
        encoding="utf-8",
    )

    result = _check_report_artifact_health(
        tmp_path,
        {
            "A_SHARE_OUTPUT_DIR": str(output_dir),
            "A_SHARE_DELIVERY_STATE_DIR": str(tmp_path / "delivery_state"),
        },
    )

    assert result.status == "warn"
    assert "pipeline_mismatch=morning expected evening" in result.detail


def test_report_artifact_health_detects_missing_evening_manifest_kind_fields(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "evening_manifest.json").write_text(
        json.dumps({"date": "20260831", "charts": {"paths": {}}}),
        encoding="utf-8",
    )

    result = _check_report_artifact_health(
        tmp_path,
        {
            "A_SHARE_OUTPUT_DIR": str(output_dir),
            "A_SHARE_DELIVERY_STATE_DIR": str(tmp_path / "delivery_state"),
        },
    )

    assert result.status == "warn"
    assert "pipeline_missing=evening" in result.detail
    assert "report_kind_missing=evening" in result.detail


def test_report_artifact_health_detects_evening_report_kind_mismatch(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "evening_manifest.json").write_text(
        json.dumps(
            {
                "pipeline": "evening",
                "report_kind": "morning",
                "date": "20260831",
                "charts": {"paths": {}},
            }
        ),
        encoding="utf-8",
    )

    result = _check_report_artifact_health(
        tmp_path,
        {
            "A_SHARE_OUTPUT_DIR": str(output_dir),
            "A_SHARE_DELIVERY_STATE_DIR": str(tmp_path / "delivery_state"),
        },
    )

    assert result.status == "warn"
    assert "report_kind_mismatch=morning expected evening" in result.detail


def test_report_artifact_health_allows_normal_morning_evening_business_dates(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    delivery_dir = tmp_path / "delivery"
    output_dir.mkdir()
    delivery_dir.mkdir()
    chart_paths = {
        key: output_dir / f"{key}.png"
        for key in ("dashboard", "moneyflow", "topic", "sentiment", "us_overnight", "weekly_chart")
    }
    for path in chart_paths.values():
        path.write_bytes(b"png")
    for name in (
        "weekly_recap.md",
        "weekly_combined_report.md",
        "value_weekly_card.png",
        "size_style_card.png",
    ):
        (output_dir / name).write_text("weekly", encoding="utf-8")
    (output_dir / "weekly_recap.meta.json").write_text(
        json.dumps({"target_trade_date": "20260901", "actual_through": "20260901"}),
        encoding="utf-8",
    )
    for kind, trade_date in (("morning", "20260831"), ("evening", "20260901")):
        (output_dir / f"{kind}_manifest.json").write_text(
            json.dumps(
                {
                    "pipeline": kind,
                    "report_kind": kind,
                    "date": trade_date,
                    "charts": {
                        "ok": list(chart_paths),
                        "failed": [],
                        "skipped": [],
                        "degraded": [],
                        "errors": {},
                        "paths": {key: str(path) for key, path in chart_paths.items()},
                    },
                }
            ),
            encoding="utf-8",
        )
        (delivery_dir / f"{kind}_latest.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "trade_date": trade_date,
                    "generated_at": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}T12:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

    result = _check_report_artifact_health(
        tmp_path,
        {
            "A_SHARE_OUTPUT_DIR": str(output_dir),
            "A_SHARE_DELIVERY_STATE_DIR": str(delivery_dir),
        },
    )

    assert result.status == "ok", result.detail
    assert "日期不一致" not in result.detail


def test_ai_key_check_reads_stable_registry_path(tmp_path: Path) -> None:
    registry = tmp_path / "api_keys.json"
    registry.write_text(
        json.dumps(
            {
                "ai_news": {
                    "provider": "glm",
                    "keys": [{"provider": "glm", "value": "real-key"}],
                },
                "alibaba_bailian": "real-key",
            }
        ),
        encoding="utf-8",
    )

    assert _api_key_flags(tmp_path / "release", {"API_KEYS_PATH": str(registry)}) == (True, True)


def _write_executable(path: Path) -> None:
    path.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_report_dataset_contract_does_not_require_ths_hot_for_composite_reports() -> None:
    from a_share_daily.deploy_check.constants import REPORT_DATASETS_OPTIONAL

    assert "ths_hot" not in REPORT_DATASETS_REQUIRED
    assert "ths_hot" in REPORT_DATASETS_OPTIONAL


def _write_pipeline_scripts(scripts_dir: Path) -> None:
    for name in SCRIPT_NAMES:
        _write_executable(scripts_dir / name)


def _write_partition(a_share_root: Path, dataset: str, trade_date: str) -> None:
    path = (
        a_share_root
        / dataset
        / f"a_share_all_{dataset}_latest"
        / "data"
        / f"trade_date={trade_date}"
    )
    path.mkdir(parents=True)
    (path / "part.parquet").write_bytes(b"test")


def test_run_checks_reports_configured_local_deployment(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    latest_dir = project_root / "data-snapshots" / "latest"
    data_root = tmp_path / "market-data-platform"
    mdp_dir = tmp_path / "market-data-platform-repo"
    a_share_root = data_root / "assets" / "tushare" / "a_share"
    hermes_scripts = tmp_path / "hermes" / "scripts"
    scripts_dir.mkdir(parents=True)
    latest_dir.mkdir(parents=True)
    a_share_root.mkdir(parents=True)
    mdp_dir.mkdir(parents=True)
    hermes_scripts.mkdir(parents=True)
    (mdp_dir / "pyproject.toml").write_text('[project]\nname = "market-data-platform"\n')
    _write_pipeline_scripts(scripts_dir)
    for name in (
        "morning_pipeline.sh",
        "evening_pipeline.sh",
        "weekly_recap.sh",
        "local_fetch_cross_market.sh",
    ):
        _write_executable(hermes_scripts / name)
    (latest_dir / "cross_market_snapshot.json").write_text("{}", encoding="utf-8")
    (latest_dir / "tushare_snapshot.json").write_text("{}", encoding="utf-8")
    for dataset in REPORT_DATASETS:
        _write_partition(a_share_root, dataset, "20260630")
    api_keys_path = project_root / "api_keys.json"
    api_keys_path.write_text(
        json.dumps({"ai_stock_picker": {"deepseek": {"api_key": "configured-for-test"}}}),
        encoding="utf-8",
    )
    api_keys_path.chmod(0o600)

    env = {
        "DATA_PLATFORM_ROOT": str(data_root),
        "MDP_DIR": str(mdp_dir),
        "HERMES_SCRIPTS_DIR": str(hermes_scripts),
        "A_SHARE_ENABLE_TUSHARE_PREMIUM": "1",
        "A_SHARE_FEISHU_CHAT_ID": "oc_test",
        "FEISHU_WEBHOOK_DAILY": "https://example.invalid/webhook",
        "ZHIPUAI_API_KEY": "glm",
        "DASHSCOPE_API_KEY": "qwen",
        "API_KEYS_PATH": str(api_keys_path),
    }
    results = run_checks(
        project_root=project_root,
        env=env,
        which=lambda _name: None,
    )

    assert exit_code(results) == 0
    assert any(item.name == "delivery target" and item.status == "ok" for item in results)
    assert any(item.name == "AI news keys" and item.status == "ok" for item in results)
    assert any(item.name == "AI stock picker key" and "已退休" in item.detail for item in results)
    assert any(item.name == "Hermes script files" and item.status == "ok" for item in results)
    assert any(item.name == "report datasets" and item.status == "ok" for item in results)
    assert any(item.name == "market-data-platform repo" and item.status == "ok" for item in results)
    assert "Summary:" in format_results(results)


def test_runtime_project_root_uses_release_when_package_is_non_editable(
    monkeypatch, tmp_path: Path
) -> None:
    release = tmp_path / "release"
    (release / "scripts").mkdir(parents=True)
    (release / "pyproject.toml").write_text("[project]\nname='market-intel'\n", encoding="utf-8")
    monkeypatch.setenv("MARKET_INTEL_ROOT", str(release))

    assert _runtime_project_root() == release.resolve()


def test_tushare_credentials_require_proxy_url_and_primary_fallback(tmp_path: Path) -> None:
    mdp_dir = tmp_path / "market-data-platform"
    mdp_dir.mkdir()
    credential_file = mdp_dir / ".env.local"
    credential_file.write_text("# credentials are injected in this test\n", encoding="utf-8")
    credential_file.chmod(0o600)

    result = _check_tushare_credentials(
        {
            "MDP_DIR": str(mdp_dir),
            "TUSHARE_TOKEN_2": "proxy-test-token",
            "TUSHARE_API_URL_2": "https://proxy.invalid",
            "TUSHARE_TOKEN": "fallback-test-token",
        }
    )

    assert result.status == "ok"
    assert "TOKEN_2+URL_2" in result.detail
    assert "兜底" in result.detail


def test_tushare_credentials_reject_unpaired_proxy_without_fallback() -> None:
    result = _check_tushare_credentials({"TUSHARE_TOKEN_2": "proxy-test-token"})

    assert result.status == "fail"
    assert "TUSHARE_API_URL_2" in result.detail


def test_run_checks_fails_when_pipeline_scripts_are_missing(tmp_path: Path) -> None:
    results = run_checks(
        project_root=tmp_path,
        env={},
        which=lambda _name: None,
    )

    assert exit_code(results) == 1
    assert any(item.name == "pipeline scripts" and item.status == "fail" for item in results)


def test_run_checks_fails_when_hermes_script_is_symlink(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    hermes_scripts = tmp_path / "hermes" / "scripts"
    outside = tmp_path / "outside"
    scripts_dir.mkdir(parents=True)
    hermes_scripts.mkdir(parents=True)
    outside.mkdir()
    _write_pipeline_scripts(scripts_dir)
    _write_executable(outside / "morning_pipeline.sh")
    (hermes_scripts / "morning_pipeline.sh").symlink_to(outside / "morning_pipeline.sh")
    _write_executable(hermes_scripts / "evening_pipeline.sh")
    _write_executable(hermes_scripts / "weekly_recap.sh")
    _write_executable(hermes_scripts / "local_fetch_cross_market.sh")

    results = run_checks(
        project_root=project_root,
        env={"HERMES_SCRIPTS_DIR": str(hermes_scripts)},
        which=lambda _name: None,
    )

    assert exit_code(results) == 1
    assert any(item.name == "Hermes script files" and item.status == "fail" for item in results)


def test_run_checks_fails_when_local_fetch_script_is_symlink(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    hermes_scripts = tmp_path / "hermes" / "scripts"
    outside = tmp_path / "outside"
    scripts_dir.mkdir(parents=True)
    hermes_scripts.mkdir(parents=True)
    outside.mkdir()
    _write_pipeline_scripts(scripts_dir)
    for name in ("morning_pipeline.sh", "evening_pipeline.sh", "weekly_recap.sh"):
        _write_executable(hermes_scripts / name)
    _write_executable(outside / "local_fetch_cross_market.sh")
    (hermes_scripts / "local_fetch_cross_market.sh").symlink_to(
        outside / "local_fetch_cross_market.sh"
    )

    results = run_checks(
        project_root=project_root,
        env={"HERMES_SCRIPTS_DIR": str(hermes_scripts)},
        which=lambda _name: None,
    )

    assert exit_code(results) == 1
    assert any(item.name == "Hermes script files" and item.status == "fail" for item in results)


def test_run_checks_fails_when_hermes_script_is_stale(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    hermes_scripts = tmp_path / "hermes" / "scripts"
    scripts_dir.mkdir(parents=True)
    hermes_scripts.mkdir(parents=True)
    _write_pipeline_scripts(scripts_dir)
    for name in ("morning_pipeline.sh", "evening_pipeline.sh", "local_fetch_cross_market.sh"):
        _write_executable(hermes_scripts / name)
    _write_executable(hermes_scripts / "weekly_recap.sh")
    (hermes_scripts / "morning_pipeline.sh").write_text(
        "#!/bin/bash\n# stale deployed copy\nexit 0\n",
        encoding="utf-8",
    )

    results = run_checks(
        project_root=project_root,
        env={"HERMES_SCRIPTS_DIR": str(hermes_scripts)},
        which=lambda _name: None,
    )

    assert exit_code(results) == 1
    assert any(
        item.name == "Hermes script files"
        and item.status == "fail"
        and "morning_pipeline.sh" in item.detail
        for item in results
    )


def test_run_checks_warns_when_report_datasets_are_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    hermes_scripts = tmp_path / "hermes" / "scripts"
    data_root = tmp_path / "market-data-platform"
    a_share_root = data_root / "assets" / "tushare" / "a_share"
    scripts_dir.mkdir(parents=True)
    hermes_scripts.mkdir(parents=True)
    a_share_root.mkdir(parents=True)
    _write_pipeline_scripts(scripts_dir)
    for name in (
        "morning_pipeline.sh",
        "evening_pipeline.sh",
        "weekly_recap.sh",
        "local_fetch_cross_market.sh",
    ):
        _write_executable(hermes_scripts / name)
    _write_partition(a_share_root, "moneyflow_ths", "20260630")

    results = run_checks(
        project_root=project_root,
        env={
            "DATA_PLATFORM_ROOT": str(data_root),
            "HERMES_SCRIPTS_DIR": str(hermes_scripts),
            "A_SHARE_ENABLE_TUSHARE_PREMIUM": "1",
        },
        which=lambda _name: None,
    )

    assert exit_code(results) == 0
    report_check = next(item for item in results if item.name == "report datasets")
    assert report_check.status == "warn"
    assert "必需增强数据" in report_check.detail


def test_run_checks_warns_when_report_datasets_lag_daily(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    hermes_scripts = tmp_path / "hermes" / "scripts"
    data_root = tmp_path / "market-data-platform"
    a_share_root = data_root / "assets" / "tushare" / "a_share"
    scripts_dir.mkdir(parents=True)
    hermes_scripts.mkdir(parents=True)
    a_share_root.mkdir(parents=True)
    _write_pipeline_scripts(scripts_dir)
    for name in (
        "morning_pipeline.sh",
        "evening_pipeline.sh",
        "weekly_recap.sh",
        "local_fetch_cross_market.sh",
    ):
        _write_executable(hermes_scripts / name)
    _write_partition(a_share_root, "daily", "20260630")
    for dataset in REPORT_DATASETS:
        _write_partition(a_share_root, dataset, "20260629")

    results = run_checks(
        project_root=project_root,
        env={
            "DATA_PLATFORM_ROOT": str(data_root),
            "HERMES_SCRIPTS_DIR": str(hermes_scripts),
            "A_SHARE_ENABLE_TUSHARE_PREMIUM": "1",
        },
        which=lambda _name: None,
    )

    report_check = next(item for item in results if item.name == "report datasets")
    assert report_check.status == "warn"
    assert "分区落后" in report_check.detail


def test_run_checks_keeps_optional_report_dataset_lag_non_blocking(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    hermes_scripts = tmp_path / "hermes" / "scripts"
    data_root = tmp_path / "market-data-platform"
    a_share_root = data_root / "assets" / "tushare" / "a_share"
    scripts_dir.mkdir(parents=True)
    hermes_scripts.mkdir(parents=True)
    a_share_root.mkdir(parents=True)
    _write_pipeline_scripts(scripts_dir)
    for name in (
        "morning_pipeline.sh",
        "evening_pipeline.sh",
        "weekly_recap.sh",
        "local_fetch_cross_market.sh",
    ):
        _write_executable(hermes_scripts / name)
    _write_partition(a_share_root, "daily", "20260630")
    for dataset in REPORT_DATASETS_REQUIRED:
        _write_partition(a_share_root, dataset, "20260630")
    for dataset in REPORT_DATASETS_OPTIONAL:
        _write_partition(a_share_root, dataset, "20260629")
    status_dir = data_root / "reports"
    status_dir.mkdir()
    (status_dir / "a_share_report_dataset_refresh_20260630.json").write_text(
        """
        {
          "trade_date": "20260630",
          "datasets": [
            {"dataset": "moneyflow_ths", "reason": "empty_result", "fallback_used": false},
            {"dataset": "kpl_list", "reason": "permission_error", "fallback_used": false}
          ]
        }
        """,
        encoding="utf-8",
    )

    results = run_checks(
        project_root=project_root,
        env={
            "DATA_PLATFORM_ROOT": str(data_root),
            "HERMES_SCRIPTS_DIR": str(hermes_scripts),
            "A_SHARE_ENABLE_TUSHARE_PREMIUM": "1",
        },
        which=lambda _name: None,
    )

    report_check = next(item for item in results if item.name == "report datasets")
    assert report_check.status == "ok"
    assert "可选增强数据降级" in report_check.detail
    assert "接口正常返回但目标日期为空" in report_check.detail
    assert "接口权限不足" in report_check.detail


def test_run_checks_skips_report_dataset_check_by_default(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    scripts_dir = project_root / "scripts"
    hermes_scripts = tmp_path / "hermes" / "scripts"
    data_root = tmp_path / "market-data-platform"
    a_share_root = data_root / "assets" / "tushare" / "a_share"
    scripts_dir.mkdir(parents=True)
    hermes_scripts.mkdir(parents=True)
    a_share_root.mkdir(parents=True)
    _write_pipeline_scripts(scripts_dir)
    for name in (
        "morning_pipeline.sh",
        "evening_pipeline.sh",
        "weekly_recap.sh",
        "local_fetch_cross_market.sh",
    ):
        _write_executable(hermes_scripts / name)
    _write_partition(a_share_root, "daily", "20260630")

    results = run_checks(
        project_root=project_root,
        env={
            "DATA_PLATFORM_ROOT": str(data_root),
            "HERMES_SCRIPTS_DIR": str(hermes_scripts),
        },
        which=lambda _name: None,
    )

    report_check = next(item for item in results if item.name == "report datasets")
    assert report_check.status == "ok"
    assert "默认关闭" in report_check.detail


def test_report_artifact_health_checks_weekly_outputs(tmp_path: Path) -> None:
    output = tmp_path / "out" / "a_share_daily"
    output.mkdir(parents=True)
    (output / "weekly_recap.md").write_text("Value\nSize-style", encoding="utf-8")
    (output / "weekly_combined_report.md").write_text("完整周报", encoding="utf-8")
    (output / "weekly_recap.meta.json").write_text(
        json.dumps({"target_trade_date": "20260828", "actual_through": "20260828"}),
        encoding="utf-8",
    )
    for name in ("value_weekly_card.png", "size_style_card.png"):
        (output / name).write_bytes(b"png")

    result = _check_report_artifact_health(
        tmp_path,
        {"A_SHARE_OUTPUT_DIR": str(output)},
    )

    assert result.status == "ok"
    assert "周报 artifact" in result.detail


def test_report_artifact_health_warns_on_incomplete_weekly_outputs(tmp_path: Path) -> None:
    output = tmp_path / "out" / "a_share_daily"
    output.mkdir(parents=True)
    (output / "weekly_recap.md").write_text("数据不足", encoding="utf-8")
    (output / "weekly_recap.meta.json").write_text(
        json.dumps({"target_trade_date": "20260828", "actual_through": "20260827"}),
        encoding="utf-8",
    )

    result = _check_report_artifact_health(
        tmp_path,
        {"A_SHARE_OUTPUT_DIR": str(output)},
    )

    assert result.status == "warn"
    assert "weekly missing_files" in result.detail
    assert "date_mismatch" in result.detail
