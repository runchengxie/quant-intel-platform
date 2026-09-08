"""Deployment checks for A-share daily reports."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from . import data_checks as _data_checks
from . import delivery_checks as _delivery_checks
from . import env_helpers as _env_helpers
from . import runtime_checks as _runtime_checks
from . import script_checks as _script_checks
from .constants import (
    HERMES_GATEWAY_PREFLIGHT_TIMER,
    HERMES_GATEWAY_SERVICE,
    HERMES_SCRIPT_NAMES,
    PREMIUM_ENV,
    PROJECT_ROOT,
    REPORT_DATASETS,
    REPORT_DATASETS_OPTIONAL,
    REPORT_DATASETS_REQUIRED,
    SCRIPT_NAMES,
    SETUP_GUIDE,
    SYSTEMD_TIMERS,
    WINDOWS_TASKS,
    CheckResult,
    RunFn,
    Status,
    WhichFn,
)
from .data_checks import (
    _check_data_lake,
    _check_mdp_dir,
    _check_minute_campaign,
    _check_report_artifact_health,
    _check_report_datasets,
    _check_snapshots,
    _check_tushare_credentials,
)
from .delivery_checks import (
    _check_ai_keys,
    _check_ai_stock_picker_key,
    _check_delivery_env,
    _check_report_delivery_contract,
    _check_watchdog_alert_env,
    _check_webhook_env,
)
from .runtime_checks import (
    _check_hermes,
    _check_hermes_gateway_systemd,
    _check_lark_cli,
    _check_systemd,
    _check_windows_tasks,
)
from .script_checks import (
    _check_hermes_script_files,
    _check_scripts,
)

__all__ = [
    "HERMES_GATEWAY_PREFLIGHT_TIMER",
    "HERMES_GATEWAY_SERVICE",
    "HERMES_SCRIPT_NAMES",
    "PREMIUM_ENV",
    "PROJECT_ROOT",
    "REPORT_DATASETS",
    "REPORT_DATASETS_OPTIONAL",
    "REPORT_DATASETS_REQUIRED",
    "SCRIPT_NAMES",
    "SETUP_GUIDE",
    "Status",
    "SYSTEMD_TIMERS",
    "WINDOWS_TASKS",
    "WhichFn",
    "RunFn",
    "CheckResult",
    "_check_ai_keys",
    "_check_ai_stock_picker_key",
    "_check_data_lake",
    "_check_delivery_env",
    "_check_report_delivery_contract",
    "_check_watchdog_alert_env",
    "_check_hermes",
    "_check_hermes_gateway_systemd",
    "_check_hermes_script_files",
    "_check_lark_cli",
    "_check_mdp_dir",
    "_check_minute_campaign",
    "_check_report_datasets",
    "_check_report_artifact_health",
    "_check_snapshots",
    "_check_scripts",
    "_check_systemd",
    "_check_tushare_credentials",
    "_check_webhook_env",
    "_check_windows_tasks",
    "run_checks",
    "format_results",
    "exit_code",
    "run_cli",
]


def run_checks(
    *,
    project_root: Path | None = None,
    env: Mapping[str, str] | None = None,
    live: bool = False,
    which: WhichFn = shutil.which,
    run: RunFn = subprocess.run,
) -> list[CheckResult]:
    """Return local deployment readiness checks."""
    project_root = project_root or _runtime_project_root()
    check_env = _env_helpers._default_env(project_root) if env is None else env
    results = [
        _script_checks._check_scripts(project_root),
        _script_checks._check_hermes_script_files(project_root, check_env),
        _data_checks._check_mdp_dir(check_env),
        _data_checks._check_tushare_credentials(check_env),
        _data_checks._check_data_lake(check_env),
        _data_checks._check_minute_campaign(check_env),
        _data_checks._check_report_datasets(check_env),
        _data_checks._check_report_artifact_health(project_root, check_env),
        _data_checks._check_snapshots(project_root),
        _delivery_checks._check_delivery_env(check_env),
        _delivery_checks._check_watchdog_alert_env(check_env),
        _delivery_checks._check_report_delivery_contract(project_root, check_env),
        _delivery_checks._check_webhook_env(check_env),
        _delivery_checks._check_ai_stock_picker_key(project_root, check_env),
        _delivery_checks._check_ai_keys(project_root, check_env),
        _runtime_checks._check_lark_cli(check_env, which),
    ]
    if live:
        if os.name == "nt":
            results.append(_runtime_checks._check_windows_tasks(run))
        else:
            results.append(_runtime_checks._check_hermes_gateway_systemd(which, run))
            results.append(_runtime_checks._check_systemd(check_env, which, run))
        results.append(_runtime_checks._check_hermes(which, run))
    return results


def _runtime_project_root() -> Path:
    """Resolve the release root when the package runs from a shared venv."""

    configured = os.environ.get("MARKET_INTEL_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    current = Path.cwd()
    if (current / "scripts").is_dir() and (current / "pyproject.toml").is_file():
        return current
    return PROJECT_ROOT


def format_results(results: Sequence[CheckResult]) -> str:
    labels = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
    lines = [f"[{labels[item.status]}] {item.name}: {item.detail}" for item in results]
    counts = {status: sum(1 for item in results if item.status == status) for status in labels}
    lines.append(f"Summary: ok={counts['ok']} warn={counts['warn']} fail={counts['fail']}")
    return "\n".join(lines)


def exit_code(results: Sequence[CheckResult], *, strict: bool = False) -> int:
    if any(item.status == "fail" for item in results):
        return 1
    if strict and any(item.status == "warn" for item in results):
        return 1
    return 0


def run_cli(*, strict: bool = False, live: bool = False) -> int:
    results = run_checks(live=live)
    print(format_results(results))
    return exit_code(results, strict=strict)
