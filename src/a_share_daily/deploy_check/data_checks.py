"""Data platform and report-dataset checks for deploy checks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from .. import freshness as _freshness
from .. import tushare_credentials as _tushare_credentials
from ..delivery import io_util
from . import constants as _constants
from . import env_helpers as _env_helpers
from .constants import (
    PREMIUM_ENV,
    REPORT_DATASETS,
    REPORT_DATASETS_OPTIONAL,
    REPORT_DATASETS_REQUIRED,
    SETUP_GUIDE,
    CheckResult,
)


def _configured_data_root(env: Mapping[str, str]) -> Path:
    raw = env.get("DATA_PLATFORM_ROOT", "").strip() or env.get("MDP_FALLBACK_ROOT", "").strip()
    return Path(raw).expanduser() if raw else Path(".market-intel-external-data-not-configured")


def _report_chart_problems(path: Path, charts: Mapping[str, object], output_dir: Path) -> list[str]:
    chart_specs = (
        io_util.MORNING_CHARTS if path.name == "morning_manifest.json" else io_util.EVENING_CHARTS
    )
    chart_keys = (
        io_util.MORNING_CHART_KEYS
        if path.name == "morning_manifest.json"
        else io_util.EVENING_CHART_KEYS
    )
    problems: list[str] = []
    for field in ("failed", "skipped", "degraded"):
        raw_values = charts.get(field, [])
        values = [str(item) for item in raw_values if item] if isinstance(raw_values, list) else []
        if values:
            problems.append(f"{path.name} {field}={','.join(values)}")
    errors = charts.get("errors", {})
    if isinstance(errors, Mapping):
        insufficient = [
            f"{key}: {value}"
            for key, value in errors.items()
            if any(token in str(value).lower() for token in ("数据不足", "insufficient", "only "))
        ]
        if insufficient:
            problems.append(f"{path.name} information_insufficient={'; '.join(insufficient)}")
    raw_paths = charts.get("paths")
    missing_files: list[str] = []
    for _label, filename in chart_specs:
        raw_path = raw_paths.get(chart_keys[filename]) if isinstance(raw_paths, Mapping) else None
        chart_path = (
            Path(raw_path).expanduser()
            if isinstance(raw_path, str) and raw_path.strip()
            else Path(filename)
        )
        if not chart_path.is_absolute():
            chart_path = output_dir / chart_path
        if not chart_path.is_file():
            missing_files.append(str(chart_path))
    if missing_files:
        problems.append(f"{path.name} missing_files={','.join(missing_files)}")
    return problems


def _report_delivery_problems(
    path: Path, project_root: Path, env: Mapping[str, str], date: str
) -> list[str]:
    kind = "morning" if path.name == "morning_manifest.json" else "evening"
    delivery_dir = Path(
        env.get(
            "A_SHARE_DELIVERY_STATE_DIR", str(project_root / "state" / "a_share_daily_delivery")
        )
    ).expanduser()
    receipt_path = delivery_dir / f"{kind}_latest.json"
    if not receipt_path.is_file():
        return [f"{path.name} delivery_receipt_missing={receipt_path}"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path.name} delivery_receipt_invalid={exc}"]
    problems = []
    if receipt.get("success") is not True:
        problems.append(f"{path.name} delivery_failed={receipt_path}")
    receipt_date = str(receipt.get("trade_date") or "").replace("-", "")
    if date and receipt_date and receipt_date != date:
        problems.append(f"{path.name} delivery_date_mismatch={receipt_date} expected={date}")
    return problems


def _weekly_artifact_problems(output_dir: Path) -> list[str]:
    required = (
        "weekly_recap.md",
        "weekly_combined_report.md",
        "weekly_recap.meta.json",
        "value_weekly_card.png",
        "size_style_card.png",
    )
    missing = [name for name in required if not (output_dir / name).is_file()]
    problems = [f"weekly missing_files={','.join(missing)}"] if missing else []
    metadata_path = output_dir / "weekly_recap.meta.json"
    if not metadata_path.is_file():
        return problems
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"weekly metadata_invalid={exc}")
        return problems
    if not isinstance(metadata, Mapping):
        problems.append("weekly metadata_invalid=object expected")
        return problems
    for key in ("target_trade_date", "actual_through"):
        if not str(metadata.get(key) or "").strip():
            problems.append(f"weekly metadata_missing={key}")
    target = str(metadata.get("target_trade_date") or "").replace("-", "")
    actual = str(metadata.get("actual_through") or "").replace("-", "")
    if target and actual and target != actual:
        problems.append(f"weekly date_mismatch=target {target}, actual {actual}")
    report = output_dir / "weekly_combined_report.md"
    if report.is_file():
        try:
            text = report.read_text(encoding="utf-8").strip()
        except OSError as exc:
            problems.append(f"weekly report_unreadable={exc}")
        else:
            if not text:
                problems.append("weekly report_empty")
            if any(token in text.lower() for token in ("数据不足", "insufficient", "only 1 week")):
                problems.append(
                    "weekly information_insufficient=report contains insufficient-data marker"
                )
    return problems


def _check_report_artifact_health(project_root: Path, env: Mapping[str, str]) -> CheckResult:
    """Check latest report manifests, files, and delivery receipts."""
    output_dir = Path(
        env.get("A_SHARE_OUTPUT_DIR", str(project_root / "out" / "a_share_daily"))
    ).expanduser()
    manifests = [output_dir / "morning_manifest.json", output_dir / "evening_manifest.json"]
    present = [path for path in manifests if path.is_file()]
    weekly_files = (
        output_dir / "weekly_recap.md",
        output_dir / "weekly_combined_report.md",
        output_dir / "weekly_recap.meta.json",
        output_dir / "value_weekly_card.png",
        output_dir / "size_style_card.png",
    )
    weekly_present = any(path.is_file() for path in weekly_files)
    if not present and not weekly_present:
        return _constants._result(
            "report artifact health",
            "warn",
            "尚无晨报/晚报 manifest 或周报 artifact，暂无法检查完整性",
        )
    problems: list[str] = []
    for path in present:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name} 无法读取: {exc}")
            continue
        date = str(payload.get("date") or "").replace("-", "")
        expected_pipeline = "morning" if path.name == "morning_manifest.json" else "evening"
        actual_pipeline = str(payload.get("pipeline") or "").strip()
        if not actual_pipeline:
            problems.append(f"{path.name} pipeline_missing={expected_pipeline}")
        elif actual_pipeline != expected_pipeline:
            problems.append(
                f"{path.name} pipeline_mismatch={actual_pipeline} expected {expected_pipeline}"
            )
        actual_report_kind = str(payload.get("report_kind") or "").strip()
        if not actual_report_kind:
            problems.append(f"{path.name} report_kind_missing={expected_pipeline}")
        elif actual_report_kind != expected_pipeline:
            problems.append(
                f"{path.name} report_kind_mismatch={actual_report_kind} expected {expected_pipeline}"
            )
        charts = payload.get("charts")
        if not isinstance(charts, Mapping):
            problems.append(f"{path.name} 缺少 charts manifest")
            continue
        problems.extend(_report_chart_problems(path, charts, output_dir))
        problems.extend(_report_delivery_problems(path, project_root, env, date))
    problems.extend(_weekly_artifact_problems(output_dir))
    if problems:
        return _constants._result("report artifact health", "warn", "；".join(problems))
    return _constants._result(
        "report artifact health",
        "ok",
        f"已检查 {len(present)} 份晨晚报 manifest和周报 artifact，图表/文字无缺失或不足标记",
    )


def _check_data_lake(env: Mapping[str, str]) -> CheckResult:
    data_root = _configured_data_root(env)
    a_share_root = data_root / "assets" / "tushare" / "a_share"
    if a_share_root.exists():
        return _constants._result("data lake", "ok", f"已找到 {a_share_root}")
    return _constants._result(
        "data lake",
        "warn",
        f"未找到 {a_share_root}。先确认 DATA_PLATFORM_ROOT/MDP_DIR，再按 {SETUP_GUIDE} 跑本机数据刷新",
    )


def _check_mdp_dir(env: Mapping[str, str]) -> CheckResult:
    raw = env.get("MDP_DIR", "").strip()
    if not raw:
        return _constants._result(
            "market-data-platform repo",
            "warn",
            f"未配置 MDP_DIR。请按 {SETUP_GUIDE} 注入 owner 仓库路径",
        )
    mdp_dir = Path(raw).expanduser()
    if (mdp_dir / "pyproject.toml").exists():
        return _constants._result("market-data-platform repo", "ok", f"已找到 {mdp_dir}")
    return _constants._result(
        "market-data-platform repo",
        "warn",
        f"未找到 {mdp_dir}。私有仓库 clone 和 MDP_DIR 配置见 {SETUP_GUIDE}",
    )


def _check_tushare_credentials(env: Mapping[str, str]) -> CheckResult:
    """Check the owner-managed proxy-first credential chain without exposing values."""

    status, detail = _tushare_credentials.credential_health(env)
    return _constants._result("TuShare credentials", status, detail)


def _latest_partition(dataset_root: Path) -> str | None:
    candidates: list[str] = []
    for base in (dataset_root / "data",):
        candidates.extend(
            item.name.split("=", 1)[1]
            for item in base.glob("trade_date=*")
            if item.is_dir() and "=" in item.name
        )
    for latest_dir in dataset_root.glob("*_latest"):
        data_dir = latest_dir / "data"
        candidates.extend(
            item.name.split("=", 1)[1]
            for item in data_dir.glob("trade_date=*")
            if item.is_dir() and "=" in item.name
        )
    return max(candidates) if candidates else None


def _load_report_refresh_status(
    data_root: Path, target_date: str | None
) -> dict[str, Mapping[str, object]]:
    if not target_date:
        return {}
    path = data_root / "reports" / f"a_share_report_dataset_refresh_{target_date}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    datasets = payload.get("datasets")
    if not isinstance(datasets, list):
        return {}
    result: dict[str, Mapping[str, object]] = {}
    for item in datasets:
        if not isinstance(item, Mapping):
            continue
        dataset = item.get("dataset")
        if isinstance(dataset, str) and dataset:
            result[dataset] = item
    return result


def _refresh_reason_suffix(refresh_status: Mapping[str, Mapping[str, object]], dataset: str) -> str:
    item = refresh_status.get(dataset)
    if not item:
        return ""
    reason = str(item.get("reason") or item.get("status") or "").strip()
    if not reason:
        return ""
    label = _freshness.REFRESH_REASON_LABELS.get(reason, reason)
    if item.get("fallback_used"):
        label = f"{label}，fallback 已尝试"
    return f"（{label}）"


def _check_report_datasets(env: Mapping[str, str]) -> CheckResult:
    if not _env_helpers._env_flag(env, PREMIUM_ENV):
        return _constants._result(
            "report datasets",
            "ok",
            "高权限 TuShare 增强数据默认关闭。设置 A_SHARE_ENABLE_TUSHARE_PREMIUM=1 后再检查主题和资金流分区",
        )

    data_root = _configured_data_root(env)
    a_share_root = data_root / "assets" / "tushare" / "a_share"
    target_date = _latest_partition(a_share_root / "daily")
    refresh_status = _load_report_refresh_status(data_root, target_date)
    latest: dict[str, str] = {}
    required_missing: list[str] = []
    required_stale: list[str] = []
    optional_missing: list[str] = []
    optional_stale: list[str] = []
    for dataset, label in REPORT_DATASETS.items():
        trade_date = _latest_partition(a_share_root / dataset)
        missing_bucket = (
            optional_missing if dataset in REPORT_DATASETS_OPTIONAL else required_missing
        )
        stale_bucket = optional_stale if dataset in REPORT_DATASETS_OPTIONAL else required_stale
        if trade_date is None:
            missing_bucket.append(
                f"{label}({dataset}){_refresh_reason_suffix(refresh_status, dataset)}"
            )
        else:
            latest[dataset] = trade_date
            if target_date is not None and trade_date < target_date:
                stale_bucket.append(
                    f"{label}({dataset})={trade_date}，目标 {target_date}"
                    f"{_refresh_reason_suffix(refresh_status, dataset)}"
                )

    optional_problems = optional_missing + optional_stale
    if not required_missing and not required_stale:
        detail = "，".join(
            f"{dataset}={trade_date}"
            for dataset, trade_date in sorted(latest.items())
            if dataset in REPORT_DATASETS_REQUIRED
        )
        if optional_problems:
            return _constants._result(
                "report datasets",
                "ok",
                f"日报必需增强数据已落盘: {detail}；可选增强数据降级: "
                f"{'；'.join(optional_problems)}。不阻断晚报发送",
            )
        return _constants._result("report datasets", "ok", f"日报增强数据已落盘: {detail}")

    present = "，".join(f"{dataset}={trade_date}" for dataset, trade_date in sorted(latest.items()))
    suffix = f"。已有 {present}" if present else ""
    problems = []
    if required_missing:
        problems.append(f"缺少 {'，'.join(required_missing)}")
    if required_stale:
        problems.append(f"分区落后 {'，'.join(required_stale)}")
    if optional_problems:
        problems.append(f"可选增强降级 {'，'.join(optional_problems)}")
    return _constants._result(
        "report datasets",
        "warn",
        f"日报增强数据未对齐最新 daily 分区: {'。'.join(problems)}。"
        f"必需增强数据会影响主题/涨停相关模块；可选增强只影响对应图表{suffix}",
    )


def _check_snapshots(project_root: Path) -> CheckResult:
    latest = project_root / "data-snapshots" / "latest"
    missing = [
        name
        for name in ("cross_market_snapshot.json", "tushare_snapshot.json")
        if not (latest / name).exists()
    ]
    if missing:
        return _constants._result("snapshots", "warn", f"缺少 latest 快照: {', '.join(missing)}")
    return _constants._result("snapshots", "ok", "跨市场和 TuShare latest 快照都存在")


def _check_minute_campaign(env: Mapping[str, str]) -> CheckResult:
    """Report the state of an optional historical TuShare minute campaign."""

    data_root = _configured_data_root(env)
    configured = env.get("TUSHARE_MINUTE_CAMPAIGN_LEDGER", "").strip()
    if configured:
        candidates = [Path(configured).expanduser()]
    else:
        candidates = sorted(
            (data_root / "metadata" / "minute_backfill").glob(
                "tushare_historical_campaign_v1_*/ledger.json"
            )
        )
    if not candidates:
        return _constants._result(
            "minute backfill campaign", "ok", "未发现已配置的历史回填 campaign"
        )
    ledger_path = candidates[-1]
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _constants._result(
            "minute backfill campaign", "warn", f"ledger 无法读取: {ledger_path}: {exc}"
        )
    health = payload.get("health")
    if not isinstance(health, Mapping):
        return _constants._result(
            "minute backfill campaign", "warn", f"ledger 缺少 health: {ledger_path}"
        )
    state = str(health.get("state") or "unknown")
    reason = str(health.get("last_reason") or "")
    streak = health.get("no_progress_streak")
    if state == "stalled":
        detail = f"历史分钟回填 stalled: {ledger_path}"
        if reason:
            detail += f"；reason={reason}"
        if streak is not None:
            detail += f"；no_progress_streak={streak}"
        return _constants._result("minute backfill campaign", "warn", detail)
    if state not in {"running", "complete", "completed", "ready", "paused"}:
        return _constants._result(
            "minute backfill campaign",
            "warn",
            f"历史分钟回填状态异常: state={state}; ledger={ledger_path}",
        )
    return _constants._result(
        "minute backfill campaign",
        "ok",
        f"历史分钟回填状态正常: state={state}; ledger={ledger_path}",
    )
