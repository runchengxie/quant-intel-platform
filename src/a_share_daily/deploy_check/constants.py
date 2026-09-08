"""Module-level constants and shared types for deploy checks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import Literal

Status = Literal["ok", "warn", "fail"]
WhichFn = Callable[[str], str | None]
RunFn = Callable[..., CompletedProcess[str]]

# ``__file__`` lives under ``<release>/src/a_share_daily/...``.  Keep the
# project root at the release directory so deployment checks can inspect the
# sibling ``scripts`` and ``data-snapshots`` directories.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_NAMES = (
    "morning_pipeline.sh",
    "evening_pipeline.sh",
    "local_fetch_cross_market.sh",
    "refresh_tushare_report_datasets.sh",
    "refresh_tushare_daily.sh",
    "refresh_weekly_style_factors.sh",
    "ensure_hermes_gateway.sh",
    "setup_cron.sh",
)
HERMES_SCRIPT_NAMES = (
    "morning_pipeline.sh",
    "evening_pipeline.sh",
    "weekly_recap.sh",
    "local_fetch_cross_market.sh",
)
SYSTEMD_TIMERS = (
    "local-fetch-cross-market.timer",
    "asia-market-refresh.timer",
    "a-share-current-publish.timer",
    "a-share-report-datasets-refresh.timer",
    "a-share-style-factor-weekly-refresh.timer",
)
SYSTEMD_SERVICES = (
    "asia-market-refresh.service",
    "a-share-current-publish.service",
    "a-share-report-datasets-refresh.service",
    "a-share-style-factor-weekly-refresh.service",
    "tushare-minute-operational-daily.service",
    "market-intel-scheduled-recovery.service",
)
HERMES_GATEWAY_SERVICE = "hermes-gateway.service"
HERMES_GATEWAY_PREFLIGHT_TIMER = "hermes-gateway-preflight.timer"
WINDOWS_TASKS = ("Market Intel Morning", "Market Intel Evening")
SETUP_GUIDE = "docs/new-machine-setup.md"
REPORT_DATASETS_REQUIRED = {
    "dc_concept": "东方财富概念",
    "dc_concept_cons": "东方财富概念成分",
    "kpl_concept_cons": "开盘啦概念成分",
    "limit_list_ths": "涨跌停明细",
}
REPORT_DATASETS_OPTIONAL = {
    "ths_hot": "同花顺热榜（DailyWatch20 独立候选池）",
    "moneyflow_ths": "资金流向图",
    "kpl_list": "开盘啦涨停池",
}
REPORT_DATASETS = REPORT_DATASETS_REQUIRED | REPORT_DATASETS_OPTIONAL
PREMIUM_ENV = "A_SHARE_ENABLE_TUSHARE_PREMIUM"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str


def _result(name: str, status: Status, detail: str) -> CheckResult:
    return CheckResult(name=name, status=status, detail=detail)
