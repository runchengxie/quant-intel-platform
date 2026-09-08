"""Delivery-window guard for scheduled morning and evening reports."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
REPORT_WINDOWS = {
    "morning": (time(6, 30), time(9, 15)),
    "evening": (time(17, 30), time(23, 30)),
}


@dataclass(frozen=True)
class DeliveryDecision:
    """One deterministic delivery or audit-only decision."""

    kind: str
    signal_date: str
    checked_at: str
    window_start: str
    window_end_exclusive: str
    mode: str
    reason: str


def delivery_decision(
    kind: str,
    *,
    signal_date: str,
    now: datetime,
    force_delivery: bool = False,
) -> DeliveryDecision:
    """Return ``deliver``, ``wait``, or ``audit_only`` for a report run."""

    if kind not in REPORT_WINDOWS:
        raise ValueError(f"unknown report kind: {kind}")
    local_now = now.astimezone(SHANGHAI)
    start, end = REPORT_WINDOWS[kind]
    today = local_now.strftime("%Y%m%d")
    clock = local_now.timetz().replace(tzinfo=None)
    if force_delivery:
        mode, reason = "deliver", "explicit_force"
    elif signal_date != today:
        mode, reason = "audit_only", "signal_date_expired"
    elif clock < start:
        mode, reason = "wait", "before_delivery_window"
    elif clock >= end:
        mode, reason = "audit_only", "delivery_window_expired"
    else:
        mode, reason = "deliver", "within_delivery_window"
    return DeliveryDecision(
        kind=kind,
        signal_date=signal_date,
        checked_at=local_now.isoformat(),
        window_start=start.strftime("%H:%M:%S"),
        window_end_exclusive=end.strftime("%H:%M:%S"),
        mode=mode,
        reason=reason,
    )


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def record_decision(state_root: Path, decision: DeliveryDecision) -> Path:
    """Persist the latest delivery-window decision for operational audits."""

    path = state_root / decision.kind / f"{decision.signal_date}.json"
    payload = {"schema_version": "report_delivery_window.v1", **asdict(decision)}
    _atomic_write_json(path, payload)
    _atomic_write_json(state_root / decision.kind / "latest.json", payload)
    return path


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(SHANGHAI)
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=SHANGHAI) if parsed.tzinfo is None else parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=tuple(REPORT_WINDOWS))
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--force-delivery", action="store_true")
    parser.add_argument("--format", choices=("mode", "json"), default="mode")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = Path(os.environ.get("MARKET_INTEL_ROOT", Path.cwd())).expanduser().resolve()
    state_root = (
        args.state_root.expanduser().resolve()
        if args.state_root
        else project_root / "state/report_delivery_window"
    )
    force = args.force_delivery or os.environ.get(
        "MARKET_INTEL_FORCE_REPORT_DELIVERY", ""
    ).lower() in {"1", "true", "yes", "on"}
    decision = delivery_decision(
        args.kind,
        signal_date=args.signal_date,
        now=_parse_now(args.as_of or os.environ.get("MARKET_INTEL_REPORT_AS_OF")),
        force_delivery=force,
    )
    record_decision(state_root, decision)
    if args.format == "json":
        print(json.dumps(asdict(decision), ensure_ascii=False, sort_keys=True))
    else:
        print(decision.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
