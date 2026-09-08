"""Market-intel recovery entrypoint for report-system stages."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from ops_common import scheduled_recovery as recovery

MARKET_INTEL_SPECS = recovery.DEFAULT_SPECS


def run(argv: Sequence[str] | None = None) -> int:
    args = recovery._parser().parse_args(argv)
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be at least 1")
    if args.cooldown_minutes < 0:
        raise SystemExit("--cooldown-minutes must be non-negative")

    now = (
        datetime.fromisoformat(args.as_of)
        if args.as_of
        else datetime.now(recovery.context_timezone())
    )
    if now.tzinfo is None:
        now = now.replace(tzinfo=recovery.context_timezone())
    context = recovery._resolve_context(args, now)
    state_root = (
        args.state_root.expanduser().resolve()
        if args.state_root
        else Path(
            os.environ.get(
                "SCHEDULED_RECOVERY_STATE_ROOT",
                str(context.project_root / "state/scheduled_recovery"),
            )
        ).expanduser().resolve()
    )
    status, receipt = recovery.reconcile(
        now=now,
        state_root=state_root,
        repair=args.repair,
        context=context,
        specs=MARKET_INTEL_SPECS,
        max_attempts=args.max_attempts,
        cooldown_minutes=args.cooldown_minutes,
        in_progress_grace_minutes=args.in_progress_grace_minutes,
        notifier=recovery._notify_recovery_failure if args.notify else None,
    )
    json.dump(receipt, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return status


if __name__ == "__main__":
    raise SystemExit(run())
