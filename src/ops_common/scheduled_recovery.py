"""Business-date freshness DAG for outage recovery.

Calendar timers remain the normal scheduler.  This coordinator runs shortly
after boot and every 45 minutes, verifies real partitions/model/report receipts,
and repairs stale stages in dependency order with bounded daily attempts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ops_common import recovery_actions, recovery_probes, recovery_state
from ops_common.business_freshness import (
    BusinessTargets,
    FreshnessContext,
    FreshnessResult,
    build_business_targets,
    load_open_dates,
    probe_stage,
    stage_target,
)
from ops_common.env import resolve_data_platform_root
from ops_common.paths import resolve_owner_path
from ops_common.report_window import delivery_decision


@dataclass(frozen=True)
class RecoverySpec:
    """One idempotent node in the business recovery DAG."""

    key: str
    layer: str
    timer: str | None
    service: str | None
    dependencies: tuple[str, ...] = ()
    optional: bool = False
    signal_open_only: bool = False
    not_before: time | None = None
    report_kind: str | None = None


DEFAULT_SPECS = (
    RecoverySpec(
        "daily_market",
        "raw_data",
        "asia-market-refresh.timer",
        "asia-market-refresh.service",
    ),
    RecoverySpec(
        "minute_market",
        "raw_data",
        "tushare-minute-operational-daily.timer",
        "tushare-minute-operational-daily.service",
        optional=True,
    ),
    RecoverySpec(
        "current_contract",
        "data_processing",
        "a-share-current-publish.timer",
        "a-share-current-publish.service",
        dependencies=("daily_market",),
    ),
    RecoverySpec(
        "report_datasets",
        "data_processing",
        "a-share-report-datasets-refresh.timer",
        "a-share-report-datasets-refresh.service",
        dependencies=("daily_market",),
    ),
    RecoverySpec(
        "cross_market",
        "report_input",
        "local-fetch-cross-market.timer",
        "local-fetch-cross-market.service",
        dependencies=("daily_market",),
        signal_open_only=True,
        not_before=time(6, 0),
    ),
    RecoverySpec(
        "morning_model",
        "model",
        "daily-watch20-producer.timer",
        "daily-watch20-producer.service",
        dependencies=("daily_market", "report_datasets"),
        signal_open_only=True,
    ),
    RecoverySpec(
        "morning_report",
        "report",
        "a-share-morning-product-supervisor-postflight.timer",
        "a-share-morning-product-supervisor-postflight.service",
        dependencies=("morning_model", "cross_market"),
        signal_open_only=True,
        not_before=time(7, 20),
        report_kind="morning",
    ),
    RecoverySpec(
        "evening_report",
        "report",
        None,
        None,
        dependencies=("current_contract", "report_datasets"),
        not_before=time(19, 20),
        report_kind="evening",
    ),
)

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
FreshnessProbe = Callable[..., FreshnessResult]
Notifier = Callable[[str], bool]

DEFAULT_IN_PROGRESS_GRACE_MINUTES = 45
_ALERTABLE_STATUSES = frozenset(
    {
        "delivery_missing",
        "stale_business_date",
        "recovery_failed",
        "delivery_unverified",
        "attempt_limit_reached",
        "not_installed",
        "probe_error",
        "stuck_in_progress",
        # Retain the previous failure fingerprint during retry cooldown so
        # duplicate alerts remain suppressible without treating cooldown as a
        # new failure message.
        "cooldown",
    }
)


# Compatibility wrappers keep the existing private module surface stable for
# callers and tests while the implementations live in focused modules.
_run_command = recovery_probes.run_command


def _read_state(path: Path, date_key: str) -> dict[str, Any]:
    return recovery_state.read_state(path, date_key)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    recovery_state.atomic_write_json(path, payload)


def _failure_fingerprint(stages: Sequence[Mapping[str, Any]]) -> str | None:
    return recovery_state.failure_fingerprint(stages, alertable_statuses=_ALERTABLE_STATUSES)


def _disabled_stage_statuses(
    specs: Sequence[RecoverySpec], requested: Sequence[str]
) -> dict[str, str]:
    return recovery_state.disabled_stage_statuses(specs, requested)


def _systemd_probe(spec: RecoverySpec, *, runner: CommandRunner) -> dict[str, str]:
    return recovery_probes.systemd_probe(spec, runner=runner)


def _active_service_entry(
    systemd: Mapping[str, str], *, local_now: datetime, grace_minutes: int
) -> dict[str, Any]:
    return recovery_probes.active_service_entry(
        systemd,
        local_now=local_now,
        grace_minutes=grace_minutes,
        timezone=context_timezone(),
    )


def _completion_pending(
    spec: RecoverySpec,
    systemd: Mapping[str, str],
    context: FreshnessContext,
    target_date: str,
) -> bool:
    return recovery_probes.completion_pending(spec, systemd, context, target_date)


def _unavailable_stage(spec: RecoverySpec, entry: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    return recovery_probes.unavailable_stage(spec, entry)


def _recent_attempt(attempts: Sequence[Mapping[str, Any]], now: datetime, cooldown: int) -> bool:
    return recovery_state.recent_attempt(attempts, now, cooldown)


def _successful_delivery_attempt(
    attempts: Sequence[Mapping[str, Any]], *, target_date: str, report_mode: str
) -> bool:
    return recovery_state.successful_delivery_attempt(
        attempts, target_date=target_date, report_mode=report_mode
    )


def _budget_attempts(
    attempts: Sequence[Mapping[str, Any]],
    *,
    spec: RecoverySpec,
    target_date: str,
    report_mode: str,
) -> list[Mapping[str, Any]]:
    return recovery_state.budget_attempts(
        attempts,
        report_kind=spec.report_kind,
        target_date=target_date,
        report_mode=report_mode,
    )


def _timer_available(probe: Mapping[str, str]) -> bool:
    return recovery_probes.timer_available(probe)


def _action_command(
    spec: RecoverySpec,
    *,
    context: FreshnessContext,
    target_date: str,
    signal_date: str,
    report_mode: str,
) -> list[str]:
    return recovery_actions.action_command(
        spec,
        context=context,
        target_date=target_date,
        signal_date=signal_date,
        report_mode=report_mode,
    )


def _probe_freshness(
    probe: FreshnessProbe,
    context: FreshnessContext,
    spec: RecoverySpec,
    *,
    target_date: str,
    signal_date: str,
    report_mode: str,
) -> FreshnessResult:
    return recovery_actions.probe_freshness(
        probe,
        context,
        spec,
        target_date=target_date,
        signal_date=signal_date,
        report_mode=report_mode,
    )


def _attempt_recovery(
    spec: RecoverySpec,
    *,
    context: FreshnessContext,
    target_date: str,
    signal_date: str,
    report_mode: str,
    local_now: datetime,
    stage_attempts: list[dict[str, Any]],
    runner: CommandRunner,
    freshness_probe: FreshnessProbe,
) -> tuple[dict[str, Any], bool]:
    return recovery_actions.attempt_recovery(
        spec,
        context=context,
        target_date=target_date,
        signal_date=signal_date,
        report_mode=report_mode,
        local_now=local_now,
        stage_attempts=stage_attempts,
        runner=runner,
        freshness_probe=freshness_probe,
    )


def _notify_recovery_failure(message: str) -> bool:
    return recovery_actions.notify_recovery_failure(message)


def _previous_attempts(state_path: Path, date_key: str) -> dict[str, list[dict[str, Any]]]:
    return recovery_state.previous_attempts(state_path, date_key)


def _reconcile_stale_stage(
    spec: RecoverySpec,
    entry: dict[str, Any],
    *,
    context: FreshnessContext,
    target_date: str,
    signal_date: str,
    report_mode: str,
    local_now: datetime,
    repair: bool,
    attempts: dict[str, list[dict[str, Any]]],
    max_attempts: int,
    cooldown_minutes: int,
    runner: CommandRunner,
    freshness_probe: FreshnessProbe,
) -> tuple[dict[str, Any], bool]:
    stage_attempts = attempts.setdefault(spec.key, [])
    budget_attempts = _budget_attempts(
        stage_attempts, spec=spec, target_date=target_date, report_mode=report_mode
    )
    if not repair:
        # Report stages have a different operational meaning from data/model
        # stages: a prior business date is expected for a morning report, but
        # a missing delivery receipt is still a delivery failure.  Keep the
        # distinction in the receipt and alert so an expired report is not
        # mistaken for a calendar-date problem.
        entry["status"] = "delivery_missing" if spec.report_kind else "stale_business_date"
        if spec.report_kind:
            entry["detail"] = "report delivery receipt is missing"
        return entry, False
    if (
        spec.report_kind
        and report_mode == "deliver"
        and _successful_delivery_attempt(
            stage_attempts, target_date=target_date, report_mode=report_mode
        )
    ):
        entry.update(
            status="delivery_unverified",
            attempt_count=len(budget_attempts),
            detail="a successful delivery action is awaiting a consistent receipt",
        )
        return entry, False
    if len(budget_attempts) >= max_attempts:
        entry.update(status="attempt_limit_reached", attempt_count=len(budget_attempts))
        return entry, False
    if _recent_attempt(budget_attempts, local_now, cooldown_minutes):
        entry.update(status="cooldown", attempt_count=len(budget_attempts))
        return entry, False
    recovery, recovered = _attempt_recovery(
        spec,
        context=context,
        target_date=target_date,
        signal_date=signal_date,
        report_mode=report_mode,
        local_now=local_now,
        stage_attempts=stage_attempts,
        runner=runner,
        freshness_probe=freshness_probe,
    )
    entry.update(recovery)
    return entry, recovered


def _stage_gate(
    spec: RecoverySpec,
    *,
    local_now: datetime,
    targets: BusinessTargets,
) -> tuple[str | None, str]:
    if spec.signal_open_only and not targets.signal_is_open:
        return "not_applicable", "deliver"
    clock = local_now.timetz().replace(tzinfo=None)
    if spec.not_before is not None and clock < spec.not_before:
        return "waiting_source_window", "deliver"
    if spec.report_kind is None:
        return None, "deliver"
    report_signal = targets.signal_date if spec.report_kind == "morning" else targets.eod_date
    decision = delivery_decision(
        spec.report_kind,
        signal_date=report_signal,
        now=local_now,
    )
    if decision.mode == "wait":
        return "waiting_delivery_window", decision.mode
    return None, decision.mode


def _reconcile_stage(
    spec: RecoverySpec,
    *,
    context: FreshnessContext,
    targets: BusinessTargets,
    local_now: datetime,
    repair: bool,
    dependencies_ok: bool,
    attempts: dict[str, list[dict[str, Any]]],
    max_attempts: int,
    cooldown_minutes: int,
    in_progress_grace_minutes: int,
    runner: CommandRunner,
    freshness_probe: FreshnessProbe,
) -> tuple[dict[str, Any], bool]:
    target_date = stage_target(spec.key, targets)
    entry: dict[str, Any] = {
        "key": spec.key,
        "layer": spec.layer,
        "dependencies": list(spec.dependencies),
        "target_date": target_date,
    }
    gate_status, report_mode = _stage_gate(spec, local_now=local_now, targets=targets)
    entry["report_mode"] = report_mode if spec.report_kind else None
    if gate_status or target_date is None:
        entry["status"] = gate_status or "not_applicable"
        return entry, True
    freshness = _probe_freshness(
        freshness_probe,
        context,
        spec,
        target_date=target_date,
        signal_date=targets.signal_date,
        report_mode=report_mode,
    )
    entry["initial_freshness"] = freshness.to_dict()
    if freshness.fresh:
        entry["status"] = "healthy"
        return entry, True
    if not dependencies_ok:
        entry["status"] = "blocked_dependency"
        return entry, False
    systemd = _systemd_probe(spec, runner=runner)
    entry["systemd_probe"] = systemd
    if systemd["service_active_state"] in {"active", "activating", "reloading"}:
        entry.update(
            _active_service_entry(
                systemd, local_now=local_now, grace_minutes=in_progress_grace_minutes
            )
        )
        return entry, False
    if not _timer_available(systemd):
        return _unavailable_stage(spec, entry)
    if _completion_pending(spec, systemd, context, target_date):
        entry.update(
            status="completion_pending",
            detail="daily_clean output is present but release receipt is not yet fresh",
        )
        return entry, False
    return _reconcile_stale_stage(
        spec,
        entry,
        context=context,
        target_date=target_date,
        signal_date=targets.signal_date,
        report_mode=report_mode,
        local_now=local_now,
        repair=repair,
        attempts=attempts,
        max_attempts=max_attempts,
        cooldown_minutes=cooldown_minutes,
        runner=runner,
        freshness_probe=freshness_probe,
    )


def _build_alert(
    *,
    previous: Mapping[str, Any],
    stages: Sequence[Mapping[str, Any]],
    failure_fingerprint: str | None,
    date_key: str,
    state_path: Path,
    notifier: Notifier | None,
) -> dict[str, Any]:
    if failure_fingerprint is None or notifier is None:
        return {"status": "not_needed"}
    if previous.get("failure_fingerprint") == failure_fingerprint:
        return {"status": "suppressed_duplicate", "fingerprint": failure_fingerprint}
    failed = ", ".join(
        f"{stage.get('key')}={stage.get('status')}"
        for stage in stages
        if stage.get("status") in _ALERTABLE_STATUSES
    )
    message = (
        "Market Intel scheduled recovery remains unhealthy\n"
        f"date={date_key} fingerprint={failure_fingerprint}\n"
        f"stages={failed}\n"
        f"receipt={state_path}"
    )
    sent = notifier(message)
    return {
        "status": "sent" if sent else "failed",
        "fingerprint": failure_fingerprint,
        "message": message,
    }


def _reconcile_stages(
    specs: Sequence[RecoverySpec],
    disabled: Mapping[str, str],
    *,
    context: FreshnessContext,
    targets: BusinessTargets,
    local_now: datetime,
    repair: bool,
    attempts: dict[str, list[dict[str, Any]]],
    max_attempts: int,
    cooldown_minutes: int,
    in_progress_grace_minutes: int,
    runner: CommandRunner,
    freshness_probe: FreshnessProbe,
) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    stages: list[dict[str, Any]] = []
    outcomes: dict[str, bool] = {}
    for spec in specs:
        if spec.key in disabled:
            stages.append(
                {
                    "key": spec.key,
                    "layer": spec.layer,
                    "dependencies": list(spec.dependencies),
                    "status": disabled[spec.key],
                }
            )
            outcomes[spec.key] = True
            continue
        dependencies_ok = all(outcomes.get(key, False) for key in spec.dependencies)
        entry, resolved = _reconcile_stage(
            spec,
            context=context,
            targets=targets,
            local_now=local_now,
            repair=repair,
            dependencies_ok=dependencies_ok,
            attempts=attempts,
            max_attempts=max_attempts,
            cooldown_minutes=cooldown_minutes,
            in_progress_grace_minutes=in_progress_grace_minutes,
            runner=runner,
            freshness_probe=freshness_probe,
        )
        stages.append(entry)
        outcomes[spec.key] = resolved
    return stages, outcomes


def reconcile(
    *,
    now: datetime,
    state_root: Path,
    repair: bool,
    context: FreshnessContext,
    targets: BusinessTargets | None = None,
    specs: Sequence[RecoverySpec] = DEFAULT_SPECS,
    max_attempts: int = 2,
    cooldown_minutes: int = 45,
    in_progress_grace_minutes: int = DEFAULT_IN_PROGRESS_GRACE_MINUTES,
    runner: CommandRunner = _run_command,
    freshness_probe: FreshnessProbe = probe_stage,
    notifier: Notifier | None = None,
    disabled_stages: Sequence[str] = (),
) -> tuple[int, dict[str, Any]]:
    """Reconcile the freshness DAG and return ``(exit_code, receipt)``."""
    local_now = now.astimezone(context_timezone())
    resolved_targets = targets or build_business_targets(local_now, context.open_dates)
    date_key = local_now.strftime("%Y%m%d")
    state_path = state_root / f"{date_key}.json"
    run_id = f"{date_key}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')}"
    heartbeat_path = state_root / "heartbeat.json"
    _atomic_write_json(
        heartbeat_path,
        {
            "schema_version": "scheduled_recovery_heartbeat.v1",
            "run_id": run_id,
            "status": "in_progress",
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "success": None,
            "receipt_path": str(state_path),
        },
    )
    previous = _read_state(state_path, date_key)
    attempts = _previous_attempts(state_path, date_key)
    disabled = _disabled_stage_statuses(specs, disabled_stages)
    stages, outcomes = _reconcile_stages(
        specs,
        disabled,
        context=context,
        targets=resolved_targets,
        local_now=local_now,
        repair=repair,
        attempts=attempts,
        max_attempts=max_attempts,
        cooldown_minutes=cooldown_minutes,
        in_progress_grace_minutes=in_progress_grace_minutes,
        runner=runner,
        freshness_probe=freshness_probe,
    )
    success = all(outcomes.values())
    failure_fingerprint = _failure_fingerprint(stages) if not success else None
    receipt: dict[str, Any] = {
        "schema_version": "scheduled_recovery.v2",
        "date": date_key,
        "checked_at": datetime.now(UTC).isoformat(),
        "timezone": "Asia/Shanghai",
        "repair": repair,
        "max_attempts_per_stage": max_attempts,
        "cooldown_minutes": cooldown_minutes,
        "business_targets": asdict(resolved_targets),
        "success": success,
        "disabled_stages": disabled,
        "run_id": run_id,
        "failure_fingerprint": failure_fingerprint,
        "stages": stages,
        "attempts": attempts,
    }
    receipt["alert"] = _build_alert(
        previous=previous,
        stages=stages,
        failure_fingerprint=failure_fingerprint if not success else None,
        date_key=date_key,
        state_path=state_path,
        notifier=notifier,
    )
    _atomic_write_json(state_path, receipt)
    _atomic_write_json(state_root / "latest.json", receipt)
    _atomic_write_json(
        heartbeat_path,
        {
            "schema_version": "scheduled_recovery_heartbeat.v1",
            "run_id": run_id,
            "status": "complete",
            "started_at": run_id.split("-", 1)[1],
            "finished_at": datetime.now(UTC).isoformat(),
            "success": success,
            "stage_counts": {
                status: sum(stage.get("status") == status for stage in stages)
                for status in sorted({str(stage.get("status")) for stage in stages})
            },
            "receipt_path": str(state_path),
        },
    )
    return (0 if success else 1), receipt


def context_timezone() -> ZoneInfo:
    return ZoneInfo("Asia/Shanghai")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--cooldown-minutes", type=int, default=45)
    parser.add_argument(
        "--in-progress-grace-minutes",
        type=int,
        default=DEFAULT_IN_PROGRESS_GRACE_MINUTES,
    )
    parser.add_argument("--notify", action="store_true")
    parser.add_argument(
        "--disable-stage",
        action="append",
        default=[],
        help="mark a stage and its downstream dependents as intentionally disabled",
    )
    parser.add_argument("--as-of", help="Asia/Shanghai timestamp in ISO-8601 format")
    return parser


def _resolve_context(args: argparse.Namespace, now: datetime) -> FreshnessContext:
    project_root = (
        (args.project_root or Path(os.environ.get("MARKET_INTEL_ROOT", Path.cwd())))
        .expanduser()
        .resolve()
    )
    data_root = (args.data_root or resolve_data_platform_root(required=True)).expanduser().resolve()
    calendar = (
        (
            args.calendar
            or data_root / "assets/tushare/a_share/trade_cal/a_share_trade_cal_latest.parquet"
        )
        .expanduser()
        .resolve()
    )
    signal_date = now.astimezone(context_timezone()).strftime("%Y%m%d")
    return FreshnessContext(
        project_root=project_root,
        data_root=data_root,
        open_dates=load_open_dates(calendar, through=signal_date),
    )


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be at least 1")
    if args.cooldown_minutes < 0:
        raise SystemExit("--cooldown-minutes must be non-negative")
    now = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(context_timezone())
    if now.tzinfo is None:
        now = now.replace(tzinfo=context_timezone())
    context = _resolve_context(args, now)
    state_root = (
        args.state_root.expanduser().resolve()
        if args.state_root
        else resolve_owner_path(
            "market-intel",
            category="state",
            override_env="SCHEDULED_RECOVERY_STATE_ROOT",
            suffix=("scheduled_recovery",),
        ).resolve()
    )
    status, receipt = reconcile(
        now=now,
        state_root=state_root,
        repair=args.repair,
        context=context,
        max_attempts=args.max_attempts,
        cooldown_minutes=args.cooldown_minutes,
        in_progress_grace_minutes=args.in_progress_grace_minutes,
        notifier=_notify_recovery_failure if args.notify else None,
        disabled_stages=args.disable_stage,
    )
    json.dump(receipt, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return status


if __name__ == "__main__":
    raise SystemExit(run())
