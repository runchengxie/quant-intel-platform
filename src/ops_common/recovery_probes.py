"""System and filesystem probes used by the recovery coordinator."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from ops_common.business_freshness import FreshnessContext


class RecoverySpecLike(Protocol):
    key: str
    timer: str | None
    service: str | None
    optional: bool


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv comes from a static stage allow-list
        list(command),
        capture_output=True,
        text=True,
        check=False,
    )


def systemd_properties(
    unit: str,
    properties: Sequence[str],
    *,
    runner: CommandRunner,
) -> dict[str, str]:
    command = ["systemctl", "--user", "show", unit]
    command.extend(f"--property={item}" for item in properties)
    result = runner(command)
    if result.returncode != 0:
        return {
            "LoadState": "not-found",
            "CommandError": (result.stderr or result.stdout).strip()[:500],
        }
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def systemd_probe(spec: RecoverySpecLike, *, runner: CommandRunner) -> dict[str, str]:
    if spec.timer is None or spec.service is None:
        return {
            "timer_load_state": "coordinator",
            "timer_unit_file_state": "enabled",
            "timer_active_state": "active",
            "service_load_state": "coordinator",
            "service_active_state": "inactive",
            "service_sub_state": "dead",
            "service_result": "unknown",
        }
    timer = systemd_properties(
        spec.timer,
        ("LoadState", "UnitFileState", "ActiveState"),
        runner=runner,
    )
    service = systemd_properties(
        spec.service,
        (
            "LoadState",
            "ActiveState",
            "SubState",
            "Result",
            "ExecMainStatus",
            "ExecMainStartTimestamp",
            "ExecMainExitTimestamp",
            "InvocationID",
        ),
        runner=runner,
    )
    return {
        "timer_load_state": timer.get("LoadState", "unknown"),
        "timer_unit_file_state": timer.get("UnitFileState", "unknown"),
        "timer_active_state": timer.get("ActiveState", "unknown"),
        "service_load_state": service.get("LoadState", "unknown"),
        "service_active_state": service.get("ActiveState", "unknown"),
        "service_sub_state": service.get("SubState", "unknown"),
        "service_result": service.get("Result", "unknown"),
        "service_exit_status": service.get("ExecMainStatus", ""),
        "service_start_timestamp": service.get("ExecMainStartTimestamp", ""),
        "service_exit_timestamp": service.get("ExecMainExitTimestamp", ""),
        "invocation_id": service.get("InvocationID", ""),
    }


def parse_systemd_timestamp(value: str, timezone: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%a %Y-%m-%d %H:%M:%S %Z")
        except ValueError:
            return None
    return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed


def current_contract_output_present(context: FreshnessContext, target_date: str) -> bool:
    root = context.data_root / "assets/tushare/a_share/daily"
    return any(
        (candidate / "data/000001.SZ.parquet").is_file()
        and (candidate / "data/000001.SZ.parquet").stat().st_size > 0
        for candidate in root.glob(f"a_share_all_*_{target_date}_daily_clean")
    )


def active_service_entry(
    systemd: Mapping[str, str], *, local_now: datetime, grace_minutes: int, timezone: ZoneInfo
) -> dict[str, Any]:
    started = parse_systemd_timestamp(systemd.get("service_start_timestamp", ""), timezone)
    runtime_seconds = max(0.0, (local_now - started).total_seconds()) if started else None
    timeout_seconds = grace_minutes * 60
    return {
        "runtime_seconds": runtime_seconds,
        "runtime_timeout_seconds": timeout_seconds,
        "status": (
            "stuck_in_progress"
            if runtime_seconds is not None and runtime_seconds >= timeout_seconds
            else "in_progress"
        ),
    }


def completion_pending(
    spec: RecoverySpecLike,
    systemd: Mapping[str, str],
    context: FreshnessContext,
    target_date: str,
) -> bool:
    return (
        spec.key == "current_contract"
        and systemd["service_active_state"] == "inactive"
        and systemd["service_result"] == "success"
        and current_contract_output_present(context, target_date)
    )


def unavailable_stage(spec: RecoverySpecLike, entry: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    entry["status"] = "optional_not_installed" if spec.optional else "not_installed"
    return entry, spec.optional


def timer_available(probe: Mapping[str, str]) -> bool:
    return probe.get("timer_load_state") in {"loaded", "coordinator"} and probe.get(
        "timer_unit_file_state"
    ) in {"enabled", "enabled-runtime"}
