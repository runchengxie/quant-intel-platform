"""Runtime checks for deploy: lark-cli, systemd, Windows tasks, Hermes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from subprocess import CompletedProcess

from . import constants as _constants
from . import env_helpers as _env_helpers
from .constants import (
    HERMES_GATEWAY_PREFLIGHT_TIMER,
    HERMES_GATEWAY_SERVICE,
    SYSTEMD_SERVICES,
    SYSTEMD_TIMERS,
    WINDOWS_TASKS,
    CheckResult,
    RunFn,
    WhichFn,
)


def _lark_cli_config_paths(env: Mapping[str, str], cli_path: str | None) -> list[Path]:
    paths = [
        Path.home() / ".lark-cli" / "config.json",
        Path.home() / ".lark-cli" / "hermes" / "config.json",
    ]

    scoop_roots: list[Path] = []
    if env.get("SCOOP", "").strip():
        scoop_roots.append(Path(env["SCOOP"]).expanduser())
    scoop_roots.append(Path.home() / "scoop")

    if cli_path:
        cli = Path(cli_path).expanduser()
        for parent in cli.parents:
            if parent.name.lower() == "scoop":
                scoop_roots.append(parent)
                break

    for root in scoop_roots:
        paths.extend(
            [
                root / "persist" / "lark-cli" / "config.json",
                root / "persist" / "lark-cli" / "hermes" / "config.json",
            ]
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def _check_lark_cli(env: Mapping[str, str], which: WhichFn) -> CheckResult:
    configured_cli = env.get("LARK_CLI", "").strip()
    cli_path = configured_cli or which("lark-cli")
    config_paths = _lark_cli_config_paths(env, cli_path)
    if cli_path and any(path.exists() for path in config_paths):
        return _constants._result("lark-cli fallback", "ok", "已找到 lark-cli 和本地配置")
    if cli_path:
        return _constants._result("lark-cli fallback", "warn", "已找到 lark-cli，未找到本地配置")
    return _constants._result("lark-cli fallback", "warn", "未找到 lark-cli")


def _systemd_user_dir(env: Mapping[str, str]) -> Path:
    config_home = Path(env.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))).expanduser()
    return config_home / "systemd" / "user"


def _timer_enabled_by_unit_file(env: Mapping[str, str], timer: str) -> bool:
    user_dir = _systemd_user_dir(env)
    return (user_dir / "timers.target.wants" / timer).exists()


def _failed_systemd_services(run: RunFn) -> list[str]:
    failed: list[str] = []
    for service in SYSTEMD_SERVICES:
        state = _env_helpers._safe_run(
            run,
            [
                "systemctl",
                "--user",
                "show",
                "--property=LoadState,ActiveState",
                "--value",
                service,
            ],
        )
        if state is None or _user_bus_unavailable(state) or state.returncode != 0:
            continue
        values = [line.strip().lower() for line in state.stdout.splitlines() if line.strip()]
        if len(values) >= 2 and values[0] == "loaded" and values[1] == "failed":
            failed.append(service)
    return failed


def _user_bus_unavailable(result: CompletedProcess[str]) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    return (
        "failed to connect to user scope bus" in text
        or "operation not permitted" in text
        or "no medium found" in text
        or "host is down" in text
    )


def _check_hermes_gateway_systemd(which: WhichFn, run: RunFn) -> CheckResult:
    if which("systemctl") is None:
        return _constants._result("Hermes Gateway systemd", "warn", "未找到 systemctl")

    issues: list[str] = []
    units = (
        (HERMES_GATEWAY_SERVICE, "Gateway service"),
        (HERMES_GATEWAY_PREFLIGHT_TIMER, "Gateway preflight timer"),
    )
    for unit, label in units:
        loaded = _env_helpers._safe_run(
            run,
            ["systemctl", "--user", "show", "--property=LoadState", "--value", unit],
        )
        if loaded is not None and _user_bus_unavailable(loaded):
            return _constants._result(
                "Hermes Gateway systemd",
                "warn",
                "当前环境无法连接 user systemd bus，无法确认 Gateway 与 preflight timer 状态",
            )
        if loaded is None or loaded.returncode != 0 or loaded.stdout.strip().lower() != "loaded":
            issues.append(f"{label} 未安装")
            continue

        enabled = _env_helpers._safe_run(run, ["systemctl", "--user", "is-enabled", unit])
        if enabled is not None and _user_bus_unavailable(enabled):
            return _constants._result(
                "Hermes Gateway systemd",
                "warn",
                "当前环境无法连接 user systemd bus，无法确认 Gateway 与 preflight timer 状态",
            )
        if enabled is None or enabled.returncode != 0:
            issues.append(f"{label} 未启用")

        active = _env_helpers._safe_run(run, ["systemctl", "--user", "is-active", "--quiet", unit])
        if active is not None and _user_bus_unavailable(active):
            return _constants._result(
                "Hermes Gateway systemd",
                "warn",
                "当前环境无法连接 user systemd bus，无法确认 Gateway 与 preflight timer 状态",
            )
        if active is None or active.returncode != 0:
            issues.append(f"{label} 未运行")

    if issues:
        return _constants._result("Hermes Gateway systemd", "warn", "；".join(issues))
    return _constants._result(
        "Hermes Gateway systemd",
        "ok",
        "Gateway service 与 06:50/18:50 preflight timer 均已安装、启用并运行",
    )


def _check_systemd(env: Mapping[str, str], which: WhichFn, run: RunFn) -> CheckResult:
    if which("systemctl") is None:
        return _constants._result("systemd timers", "warn", "未找到 systemctl")
    missing: list[str] = []
    unit_file_confirmed: list[str] = []
    bus_unavailable = False
    for timer in SYSTEMD_TIMERS:
        result = _env_helpers._safe_run(run, ["systemctl", "--user", "is-enabled", timer])
        if result is not None and result.returncode == 0:
            continue
        if (
            result is not None
            and _user_bus_unavailable(result)
            and _timer_enabled_by_unit_file(env, timer)
        ):
            bus_unavailable = True
            unit_file_confirmed.append(timer)
            continue
        if result is not None and _user_bus_unavailable(result):
            bus_unavailable = True
        if result is None or result.returncode != 0:
            missing.append(timer)
    if missing:
        if bus_unavailable:
            return _constants._result(
                "systemd timers",
                "warn",
                f"当前环境无法连接 user systemd bus，且未找到启用 unit: {', '.join(missing)}",
            )
        return _constants._result("systemd timers", "warn", f"未启用: {', '.join(missing)}")
    failed_services = _failed_systemd_services(run)
    if failed_services:
        return _constants._result(
            "systemd timers",
            "warn",
            f"已启用 timer 的 service failed: {', '.join(failed_services)}",
        )
    if unit_file_confirmed:
        return _constants._result(
            "systemd timers",
            "ok",
            "本地补抓 timer 已启用（通过 unit 文件确认，当前环境无法连接 user systemd bus）",
        )
    return _constants._result("systemd timers", "ok", "本地补抓 timer 已启用")


def _check_windows_tasks(run: RunFn) -> CheckResult:
    missing: list[str] = []
    for task in WINDOWS_TASKS:
        try:
            result = run(
                ["schtasks", "/Query", "/TN", task],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception:
            return _constants._result("Windows scheduled tasks", "warn", "无法运行 schtasks")
        if result.returncode != 0:
            missing.append(task)
    if missing:
        return _constants._result(
            "Windows scheduled tasks",
            "warn",
            f"未找到: {', '.join(missing)}。运行 scripts/windows/install_scheduled_tasks.ps1 -Force",
        )
    return _constants._result("Windows scheduled tasks", "ok", "晨报和晚报 Windows 定时任务都存在")


def _check_hermes(which: WhichFn, run: RunFn) -> CheckResult:
    if which("hermes") is None:
        return _constants._result("Hermes cron", "warn", "未找到 hermes CLI")
    result = _env_helpers._safe_run(run, ["hermes", "cron", "list"])
    if result is None or result.returncode != 0:
        return _constants._result("Hermes cron", "warn", "无法读取 Hermes cron list")
    output = f"{result.stdout}\n{result.stderr}"
    morning_ok = "晨间" in output or "morning" in output.lower()
    evening_ok = "盘后" in output or "evening" in output.lower()
    if morning_ok and evening_ok:
        return _constants._result("Hermes cron", "ok", "晨报和晚报 cron 都可见")
    missing = []
    if not morning_ok:
        missing.append("晨报")
    if not evening_ok:
        missing.append("晚报")
    return _constants._result("Hermes cron", "warn", f"未在 cron list 中看到: {', '.join(missing)}")
