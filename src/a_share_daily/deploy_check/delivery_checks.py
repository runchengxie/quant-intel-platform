"""Delivery, webhook, and AI-key checks for deploy checks."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from . import constants as _constants
from . import env_helpers as _env_helpers
from .constants import CheckResult


def _check_delivery_env(env: Mapping[str, str]) -> CheckResult:
    if _env_helpers._env_value(env, "A_SHARE_HERMES_TARGET", "HERMES_SEND_TARGET"):
        return _constants._result("delivery target", "ok", "已配置 Hermes send 目标")
    if _env_helpers._env_value(
        env,
        "MARKET_INTEL_CLIENT_CHAT_ID",
        "MARKET_INTEL_INTERNAL_CHAT_ID",
        "MARKET_INTEL_PUBLIC_CHAT_ID",
    ):
        return _constants._result("delivery target", "ok", "已配置分群飞书 chat ID")
    if _env_helpers._env_value(env, "A_SHARE_FEISHU_CHAT_ID", "FEISHU_CHAT_ID"):
        return _constants._result(
            "delivery target", "ok", "已配置飞书 chat ID，可派生 Hermes/lark-cli 目标"
        )
    return _constants._result("delivery target", "warn", "缺少 Hermes send 目标或飞书 chat ID")


def _check_watchdog_alert_env(env: Mapping[str, str]) -> CheckResult:
    """Check the personal Feishu target used by supervisor/watchdog alerts."""
    if _env_helpers._env_value(env, "WATCHDOG_ALERT_FEISHU_CHAT_ID", "A_SHARE_FEISHU_DM_CHAT_ID"):
        return _constants._result(
            "watchdog alert target", "ok", "已配置 supervisor/watchdog 个人告警目标"
        )
    return _constants._result(
        "watchdog alert target",
        "warn",
        "缺少 WATCHDOG_ALERT_FEISHU_CHAT_ID 或 A_SHARE_FEISHU_DM_CHAT_ID；失败告警可能无法发送",
    )


def _check_webhook_env(env: Mapping[str, str]) -> CheckResult:
    if _env_helpers._env_value(
        env, "FEISHU_WEBHOOK_DAILY", "FEISHU_WEBHOOK_ALERTS", "FEISHU_WEBHOOK"
    ):
        return _constants._result("webhook fallback", "ok", "已配置飞书 webhook 文字兜底")
    return _constants._result("webhook fallback", "warn", "未配置飞书 webhook，纯文字兜底不可用")


def _check_ai_keys(project_root: Path, env: Mapping[str, str]) -> CheckResult:
    glm_ok, aliyun_ok = _env_helpers._api_key_flags(project_root, env)
    if glm_ok and aliyun_ok:
        return _constants._result("AI news keys", "ok", "GLM 主通道和阿里/Qwen 兜底都已配置")
    if glm_ok:
        return _constants._result("AI news keys", "warn", "已配置 GLM，未检测到阿里/Qwen 兜底")
    return _constants._result("AI news keys", "warn", "未检测到 GLM key，新闻抓取会降级")


def _check_ai_stock_picker_key(project_root: Path, env: Mapping[str, str]) -> CheckResult:
    del project_root, env
    return _constants._result("AI stock picker key", "ok", "AI精选（新）已退休；无需配置")


def _check_report_delivery_contract(project_root: Path, env: Mapping[str, str]) -> CheckResult:
    """Check the no-send delivery contract used by scheduled reports."""
    morning = project_root / "scripts/morning_pipeline.sh"
    evening = project_root / "scripts/evening_pipeline.sh"
    weekly = project_root / "scripts/weekly_recap.sh"
    required = (morning, evening, weekly)
    if any(not path.is_file() for path in required):
        missing = ", ".join(path.name for path in required if not path.is_file())
        return _constants._result("report delivery contract", "warn", f"缺少脚本：{missing}")

    from a_share_daily.delivery import io_util

    problems: list[str] = []
    if len(io_util.MORNING_CHARTS) != 6:
        problems.append(f"晨报图表定义为 {len(io_util.MORNING_CHARTS)} 张，应为 6 张")
    if len(io_util.EVENING_CHARTS) != 6:
        problems.append(f"晚报图表定义为 {len(io_util.EVENING_CHARTS)} 张，应为 6 张")
    if not _env_helpers._env_flag(env, "A_SHARE_REQUIRE_COMPLETE_CHARTS"):
        problems.append("未开启晨报/晚报完整图表门禁")
    if not _env_helpers._env_flag(env, "MORNING_REQUIRE_SELECTION_DELIVERY"):
        problems.append("未开启晨报两套选股失败门禁")
    if not _env_helpers._env_flag(env, "A_SHARE_WEEKLY_REQUIRE_SIZE_STYLE"):
        problems.append("未开启周报小盘报告门禁")
    morning_text = morning.read_text(encoding="utf-8")
    evening_text = evening.read_text(encoding="utf-8")
    weekly_text = weekly.read_text(encoding="utf-8")
    for label, text, needles in (
        (
            "晨报",
            morning_text,
            ("daily_watch20_delivery.sh", "d11_h5_shadow_delivery", "report_delivery morning"),
        ),
        ("晚报", evening_text, ("report_delivery evening",)),
        (
            "周报",
            weekly_text,
            ("weekly-analysis value", "weekly-analysis size-style", "size_style.md"),
        ),
    ):
        missing = [needle for needle in needles if needle not in text]
        if missing:
            problems.append(f"{label}缺少链路：{', '.join(missing)}")

    if not _env_helpers._env_value(env, "MARKET_INTEL_INTERNAL_CHAT_ID"):
        problems.append("未配置内部测试群目标")
    if not _env_helpers._env_value(env, "MARKET_INTEL_CLIENT_CHAT_ID"):
        problems.append("未配置 client audience 目标")
    if not _env_helpers._env_value(
        env,
        "MARKET_INTEL_INTERNAL_CHAT_ID",
    ):
        problems.append("未配置周报目标")
    if problems:
        return _constants._result("report delivery contract", "warn", "；".join(problems))
    return _constants._result(
        "report delivery contract",
        "ok",
        "晨报 6 图+文字+两套选股、晚报 6 图+文字、周报价值+小盘链路和目标均已配置",
    )
