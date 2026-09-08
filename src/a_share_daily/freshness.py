"""Freshness contracts and report rendering for A-share daily reports."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

FreshnessStatus = Literal[
    "fresh",
    "expected_delay",
    "stale",
    "missing",
    "optional_stale",
    "optional_missing",
    "skipped",
]
FreshnessPolicy = Literal["same_day", "allowed_lag", "flat"]
DatasetTier = Literal["core", "enhanced", "optional"]

DEFAULT_REFRESH_ATTEMPTS = (
    "github_snapshot",
    "windows_task_refresh",
    "report_pipeline_refresh",
)
ATTEMPT_LABELS = {
    "github_snapshot": "GitHub Actions 快照",
    "local_scheduled_refresh": "本机定时补抓",
    "windows_task_refresh": "Windows Task Scheduler 补抓",
    "report_pipeline_refresh": "报告流水线最终补抓",
    "manual_generation": "手动生成",
}


@dataclass(frozen=True)
class DatasetContract:
    key: str
    label: str
    policy: FreshnessPolicy = "same_day"
    allowed_lag_days: int = 0
    note: str = ""
    tier: DatasetTier = "core"


DATASET_CONTRACTS: dict[str, DatasetContract] = {
    "daily": DatasetContract("daily", "A股日线"),
    "daily_basic": DatasetContract("daily_basic", "A股基础指标"),
    "adj_factor": DatasetContract("adj_factor", "复权因子"),
    "limit_status": DatasetContract("limit_status", "涨跌停状态"),
    "hsgt_top10": DatasetContract(
        "hsgt_top10",
        "沪深港通十大成交",
        policy="allowed_lag",
        allowed_lag_days=4,
        note="沪深港通成交数据可能受官方披露节奏影响",
        tier="optional",
    ),
    "moneyflow_ths": DatasetContract("moneyflow_ths", "同花顺资金流", tier="optional"),
    "limit_list_ths": DatasetContract("limit_list_ths", "涨跌停明细", tier="enhanced"),
    "dc_concept": DatasetContract("dc_concept", "东方财富概念", tier="enhanced"),
    "dc_concept_cons": DatasetContract("dc_concept_cons", "东方财富概念成分", tier="enhanced"),
    "kpl_concept_cons": DatasetContract("kpl_concept_cons", "开盘啦概念成分", tier="enhanced"),
    "ths_hot": DatasetContract("ths_hot", "同花顺热榜", tier="enhanced"),
    "kpl_list": DatasetContract("kpl_list", "开盘啦涨停池", tier="optional"),
    "margin": DatasetContract(
        "margin",
        "融资融券余额",
        policy="allowed_lag",
        allowed_lag_days=2,
        note="融资融券数据允许 T+1/T+2 官方延迟",
        tier="optional",
    ),
    "margin_detail": DatasetContract(
        "margin_detail",
        "融资融券明细",
        policy="allowed_lag",
        allowed_lag_days=2,
        note="融资融券明细允许 T+1/T+2 官方延迟",
        tier="optional",
    ),
    "index_daily": DatasetContract(
        "index_daily",
        "指数日线",
        policy="flat",
        note="flat parquet，存在即视为可用",
    ),
    "ths_member": DatasetContract(
        "ths_member",
        "同花顺行业成分",
        policy="flat",
        note="flat parquet，存在即视为可用",
    ),
}

REFRESH_REASON_LABELS = {
    "partition_ready": "目标分区已落盘",
    "fallback_success": "参数 fallback 成功",
    "empty_result": "接口正常返回但目标日期为空",
    "permission_error": "接口权限不足",
    "timeout": "请求超时或被冷却",
    "command_error": "补抓命令异常退出",
    "no_partition": "补抓结束但未生成目标分区",
    "premium_disabled": "高权限数据未启用",
    "disabled_by_config": "已按配置暂时关闭",
}


def _split_attempts(value: str | None = None) -> list[str]:
    raw = value if value is not None else os.environ.get("A_SHARE_DATA_REFRESH_ATTEMPTS", "")
    attempts = [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]
    return attempts or list(DEFAULT_REFRESH_ATTEMPTS)


def _attempt_rows(attempts: Sequence[str]) -> list[dict[str, str]]:
    return [
        {
            "name": attempt,
            "label": ATTEMPT_LABELS.get(attempt, attempt),
            "status": "completed",
        }
        for attempt in attempts
    ]


def _parse_date(value: str | None) -> datetime | None:
    if not value or len(value) != 8 or not value.isdigit():
        return None
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None


def _date_dash(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or "n/a"


def _refresh_detail(refresh_info: Mapping[str, Any] | None) -> str:
    if not refresh_info:
        return ""
    reason = str(refresh_info.get("reason") or refresh_info.get("status") or "").strip()
    if not reason:
        return ""
    label = REFRESH_REASON_LABELS.get(reason, reason)
    fallback = "；使用 fallback 参数" if refresh_info.get("fallback_used") else ""
    return f"{label}{fallback}"


def _evaluate_dataset(
    *,
    key: str,
    latest: str | None,
    target_date: str | None,
    attempts: Sequence[str],
    refresh_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = DATASET_CONTRACTS.get(key, DatasetContract(key, key))
    actual = latest if latest and latest != "MISSING" else None
    expected = target_date if contract.policy != "flat" else None
    status: FreshnessStatus
    detail = ""

    if actual is None:
        status = "missing"
        detail = "未找到可用分区"
    elif contract.policy == "flat":
        status = "fresh"
        detail = contract.note or "flat 数据可用"
    elif target_date is None:
        status = "fresh"
        detail = "未指定目标交易日，仅检查可用性"
    elif actual >= target_date:
        status = "fresh"
        detail = "已对齐目标交易日"
    else:
        actual_dt = _parse_date(actual)
        target_dt = _parse_date(target_date)
        lag_days = (target_dt - actual_dt).days if actual_dt and target_dt else None
        if (
            contract.policy == "allowed_lag"
            and lag_days is not None
            and lag_days <= contract.allowed_lag_days
        ):
            status = "expected_delay"
            detail = contract.note or f"允许滞后 {contract.allowed_lag_days} 天"
        else:
            status = "stale"
            detail = "补抓后仍旧"

    refresh_detail = _refresh_detail(refresh_info)
    if status in {"stale", "missing"} and refresh_detail:
        detail = refresh_detail
    if status in {"stale", "missing"} and contract.tier == "optional":
        status = "optional_missing" if status == "missing" else "optional_stale"
        if not refresh_detail:
            detail = f"{detail}；可选增强数据降级"

    return {
        "dataset": key,
        "label": contract.label,
        "policy": contract.policy,
        "tier": contract.tier,
        "latest": actual or "MISSING",
        "expected": expected,
        "status": status,
        "detail": detail,
        "allowed_lag_days": contract.allowed_lag_days,
        "attempts": _attempt_rows(attempts),
        "refresh": dict(refresh_info or {}),
    }


def _skipped_dataset_row(
    *,
    key: str,
    latest: str | None,
    target_date: str | None,
    reason: str,
) -> dict[str, Any]:
    contract = DATASET_CONTRACTS.get(key, DatasetContract(key, key))
    detail = REFRESH_REASON_LABELS.get(reason, reason)
    return {
        "dataset": key,
        "label": contract.label,
        "policy": contract.policy,
        "tier": contract.tier,
        "latest": latest or "SKIPPED",
        "expected": target_date,
        "status": "skipped",
        "detail": detail,
        "allowed_lag_days": contract.allowed_lag_days,
        "attempts": [],
        "refresh": {"reason": reason},
    }


def build_freshness_report(
    *,
    latest_by_dataset: Mapping[str, str | None],
    target_date: str | None,
    premium_enabled: bool,
    skipped_datasets: Sequence[str] = (),
    attempts: Sequence[str] | None = None,
    refresh_status_by_dataset: Mapping[str, Mapping[str, Any]] | None = None,
    skip_reason_by_dataset: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a structured freshness manifest from latest dataset dates."""
    attempt_names = list(attempts) if attempts is not None else _split_attempts()
    refresh_status_by_dataset = refresh_status_by_dataset or {}
    skip_reason_by_dataset = skip_reason_by_dataset or {}
    skipped = set(skipped_datasets)
    contracts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, latest in latest_by_dataset.items():
        seen.add(key)
        if key in skipped:
            contracts.append(
                _skipped_dataset_row(
                    key=key,
                    latest=latest,
                    target_date=target_date,
                    reason=skip_reason_by_dataset.get(key, "premium_disabled"),
                )
            )
            continue
        contracts.append(
            _evaluate_dataset(
                key=key,
                latest=latest,
                target_date=target_date,
                attempts=attempt_names,
                refresh_info=refresh_status_by_dataset.get(key),
            )
        )
    for key in sorted(skipped - seen):
        contracts.append(
            _skipped_dataset_row(
                key=key,
                latest=None,
                target_date=target_date,
                reason=skip_reason_by_dataset.get(key, "premium_disabled"),
            )
        )

    issues = [item for item in contracts if item.get("status") in {"stale", "missing"}]
    optional_issues = [
        item for item in contracts if item.get("status") in {"optional_stale", "optional_missing"}
    ]
    expected_delay = [item for item in contracts if item.get("status") == "expected_delay"]
    return {
        "ok": not issues,
        "target_date": target_date,
        "datasets": {key: latest or "MISSING" for key, latest in latest_by_dataset.items()},
        "contracts": contracts,
        "issues": issues,
        "optional_issues": optional_issues,
        "expected_delay": expected_delay,
        "attempts": _attempt_rows(attempt_names),
        "premium_tushare_enabled": premium_enabled,
        "skipped_datasets": list(skipped_datasets),
    }


def _dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list) else []


def _attempt_summary(item: Mapping[str, Any]) -> str:
    labels = [
        str(attempt.get("label") or attempt.get("name"))
        for attempt in _list(item.get("attempts"))
        if isinstance(attempt, Mapping)
    ]
    if not labels:
        return "当前生成流程"
    return " + ".join(labels)


def _market_dates(news_payload: Mapping[str, Any] | None) -> dict[str, str]:
    if not news_payload:
        return {}
    markets = _dict(news_payload.get("markets"))
    result: dict[str, str] = {}
    for key, value in markets.items():
        if not isinstance(key, str) or not isinstance(value, Mapping):
            continue
        date_value = value.get("date")
        if isinstance(date_value, str) and date_value:
            result[key] = date_value
    return result


def render_freshness_section(
    manifest_payload: Mapping[str, Any],
    news_payload: Mapping[str, Any] | None = None,
    *,
    title: str = "数据质量",
) -> list[str]:
    """Render a compact freshness section for morning/evening markdown reports."""
    lines = [f"## {title}"]
    freshness = _dict(manifest_payload.get("freshness"))
    if not freshness:
        lines.append("- [WARN] 缺少结构化数据新鲜度 manifest。")
        return lines

    contracts = [item for item in _list(freshness.get("contracts")) if isinstance(item, Mapping)]
    target_date = str(freshness.get("target_date") or manifest_payload.get("date") or "")
    fresh_count = sum(1 for item in contracts if item.get("status") == "fresh")
    expected_count = sum(1 for item in contracts if item.get("status") == "expected_delay")
    skipped_items = [item for item in contracts if item.get("status") == "skipped"]
    issue_items = [item for item in contracts if item.get("status") in {"stale", "missing"}]
    optional_items = [
        item for item in contracts if item.get("status") in {"optional_stale", "optional_missing"}
    ]
    lines.append(
        "- [fetch] "
        f"目标交易日 {_date_dash(target_date)}；"
        f"fresh {fresh_count} 项，expected_delay {expected_count} 项，"
        f"skipped {len(skipped_items)} 项，stale/missing {len(issue_items)} 项，"
        f"optional_degraded {len(optional_items)} 项。"
    )

    market_dates = _market_dates(news_payload)
    if market_dates:
        asia_dates = [
            market_dates[market] for market in ("cn", "jp", "kr") if market in market_dates
        ]
        us_date = market_dates.get("us")
        if asia_dates:
            lines.append("- [fetch] 亚洲市场新闻口径: " + "，".join(sorted(set(asia_dates))) + "。")
        if us_date:
            lines.append(f"- [fetch] 美股新闻/盘前口径: {us_date}（上一可用美股交易日）。")

    for item in issue_items[:6]:
        attempts = _attempt_summary(item)
        latest = str(item.get("latest") or "MISSING")
        expected = str(item.get("expected") or target_date or "n/a")
        detail = str(item.get("detail") or f"状态 {item.get('status')}")
        lines.append(
            "- [WARN] "
            f"{item.get('label')}({item.get('dataset')}) 最新 {latest}，目标 {expected}；"
            f"{attempts} 后仍未更新，{detail}。"
        )

    for item in optional_items[:6]:
        latest = str(item.get("latest") or "MISSING")
        expected = str(item.get("expected") or target_date or "n/a")
        detail = str(item.get("detail") or "可选增强数据未对齐")
        lines.append(
            "- [fetch] "
            f"可选增强数据 {item.get('label')}({item.get('dataset')}) 最新 {latest}，"
            f"目标 {expected}；{detail}，报告已降级，不阻断发送。"
        )

    for item in [entry for entry in contracts if entry.get("status") == "expected_delay"][:4]:
        lines.append(
            "- [fetch] "
            f"{item.get('label')}({item.get('dataset')}) 最新 {item.get('latest')}；"
            f"{item.get('detail')}。"
        )

    if skipped_items:
        skipped_labels = []
        for item in skipped_items[:8]:
            detail = str(item.get("detail") or "已跳过")
            skipped_labels.append(f"{item.get('label')}({item.get('dataset')})：{detail}")
        suffix = " 等" if len(skipped_items) > len(skipped_labels) else ""
        lines.append("- [fetch] 已跳过 " + "，".join(skipped_labels) + suffix + "。")

    if not issue_items and not expected_count and not skipped_items and not optional_items:
        lines.append("- [OK] 所有启用数据源均已对齐目标交易日或 flat 可用。")
    return lines
