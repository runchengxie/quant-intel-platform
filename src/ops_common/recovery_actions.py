"""Recovery commands and notification actions."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ops_common.business_freshness import (
    FreshnessContext,
    FreshnessResult,
    missing_daily_sessions,
    write_report_audit,
)
from ops_common.recovery_state import budget_attempts


class RecoverySpecLike(Protocol):
    key: str
    report_kind: str | None


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
FreshnessProbe = Callable[..., FreshnessResult]


def notify_recovery_failure(message: str) -> bool:
    chat_id = (
        os.environ.get("WATCHDOG_ALERT_FEISHU_CHAT_ID", "").strip()
        or os.environ.get("A_SHARE_FEISHU_DM_CHAT_ID", "").strip()
    )
    lark_cli = os.environ.get("LARK_CLI", str(Path.home() / ".local/bin/lark-cli"))
    if not chat_id or not Path(lark_cli).is_file():
        return False
    key = "scheduled-recovery-" + hashlib.sha256(message.encode("utf-8")).hexdigest()[:24]
    try:
        result = subprocess.run(  # noqa: S603 - command uses a fixed argv shape
            [
                lark_cli,
                "im",
                "+messages-send",
                "--chat-id",
                chat_id,
                "--msg-type",
                "text",
                "--text",
                message,
                "--idempotency-key",
                key,
                "--as",
                "bot",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def action_command(
    spec: RecoverySpecLike,
    *,
    context: FreshnessContext,
    target_date: str,
    signal_date: str,
    report_mode: str,
) -> list[str]:
    missing = (
        ",".join(missing_daily_sessions(context, target_date)) if spec.key == "daily_market" else ""
    )
    return [
        str(context.project_root / "scripts/recover_business_stage.sh"),
        spec.key,
        target_date,
        signal_date,
        report_mode,
        missing,
    ]


def probe_freshness(
    probe: FreshnessProbe,
    context: FreshnessContext,
    spec: RecoverySpecLike,
    *,
    target_date: str,
    signal_date: str,
    report_mode: str,
) -> FreshnessResult:
    try:
        return probe(
            context,
            stage_key=spec.key,
            target_date=target_date,
            signal_date=signal_date,
            report_mode=report_mode,
        )
    except Exception as exc:  # noqa: BLE001 - probe errors belong in the receipt
        return FreshnessResult(
            fresh=False,
            status="probe_error",
            target_date=target_date,
            actual_date=None,
            detail=f"{type(exc).__name__}: {exc}"[:500],
        )


def attempt_recovery(
    spec: RecoverySpecLike,
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
    command = action_command(
        spec,
        context=context,
        target_date=target_date,
        signal_date=signal_date,
        report_mode=report_mode,
    )
    result = runner(command)
    stage_attempts.append(
        {
            "started_at": local_now.astimezone(UTC).isoformat(),
            "target_date": target_date,
            "signal_date": signal_date,
            "report_mode": report_mode,
            "returncode": result.returncode,
            "detail": (result.stderr or result.stdout).strip()[-1000:],
        }
    )
    budget = budget_attempts(
        stage_attempts,
        report_kind=spec.report_kind,
        target_date=target_date,
        report_mode=report_mode,
    )
    if result.returncode == 0 and spec.report_kind and report_mode == "audit_only":
        report_signal = signal_date if spec.report_kind == "morning" else target_date
        write_report_audit(
            context,
            kind=spec.report_kind,
            source_date=target_date,
            signal_date=report_signal,
            reason="delivery_window_expired",
        )
    final = probe_freshness(
        freshness_probe,
        context,
        spec,
        target_date=target_date,
        signal_date=signal_date,
        report_mode=report_mode,
    )
    recovered = result.returncode == 0 and final.fresh
    return {
        "attempt_count": len(budget),
        "action": command,
        "action_returncode": result.returncode,
        "final_freshness": final.to_dict(),
        "status": (
            "audit_generated"
            if recovered and report_mode == "audit_only"
            else "recovered"
            if recovered
            else "recovery_failed"
        ),
    }, recovered
