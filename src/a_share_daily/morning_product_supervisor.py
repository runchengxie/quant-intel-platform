"""Self-healing supervisor for the two scheduled morning stock products.

This is an INTERNAL operations/debug watchdog and self-healing supervisor, not a
user-facing business alerting system. Its alerts are delivered only to the
operations (运维) Feishu channel for engineering self-checks; they are NOT
reader-facing market forecasts or trading signals.

Exit codes:
  0  normal — both products healthy, no recovery needed
  1  supervise detected a problem and attempted recovery (may have succeeded)
  3  lock conflict — another supervisor instance is already running
  4  alert dispatch failed — when the Feishu alert cannot be sent, the process
     exits non-zero so systemd marks the unit failed; the independent freshness
     watchdog then escalates. This is intentional escalation signaling, not a bug.

A send is considered *successful* only when lark-cli returns 0 AND a lightweight
``lark-cli whoami`` reachability probe confirms the bot credential is live
(enhancement: a 0 return code alone is no longer trusted, since a stale/invalid
token can make lark-cli return 0 while the message is silently dropped).
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ops_common.env import resolve_data_platform_root

from .trading_calendar import TradingCalendarError, is_open_trading_day

Probe = Callable[[], dict[str, Any]]
Recovery = Callable[[], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SupervisorConfig:
    project_root: Path
    data_root: Path
    state_root: Path
    phase: str
    signal_date: str
    max_recovery_attempts: int
    retry_delay_seconds: float
    recover: bool
    notify: bool


def _env_truthy(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _default_project_root() -> Path:
    return Path(
        os.environ.get("MARKET_INTEL_ROOT", str(Path(__file__).resolve().parents[2]))
    ).expanduser()


def _default_data_root() -> Path:
    return resolve_data_platform_root(required=True)


def _default_state_root(project_root: Path) -> Path:
    explicit = os.environ.get("MORNING_SUPERVISOR_STATE_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    delivery_state = os.environ.get("A_SHARE_DELIVERY_STATE_DIR", "").strip()
    if delivery_state:
        return Path(delivery_state).expanduser() / "morning_product_supervisor"
    return project_root / "state/morning_product_supervisor"


def _latest_data_lake_trade_date(data_root: Path) -> str | None:
    partition_root = data_root / "assets/tushare/a_share/daily/a_share_all_daily_latest/data"
    if not partition_root.is_dir():
        return None
    dates = [
        path.name.removeprefix("trade_date=")
        for path in partition_root.glob("trade_date=*")
        if len(path.name) == len("trade_date=") + 8 and path.name[11:].isdigit()
    ]
    return max(dates) if dates else None


def _trade_calendar_path(data_root: Path) -> Path:
    explicit = os.environ.get("A_SHARE_TRADE_CAL_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return data_root / "assets/tushare/a_share/trade_cal/a_share_trade_cal_latest.parquet"


def _command_result(
    *,
    label: str,
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "label": label,
            "ok": False,
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "detail": f"timeout after {exc.timeout}s",
        }
    except OSError as exc:
        return {
            "label": label,
            "ok": False,
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "detail": f"{exc.__class__.__name__}: {exc}",
        }
    output = "\n".join(value.strip() for value in (result.stdout, result.stderr) if value.strip())
    return {
        "label": label,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "detail": output[-1600:] if output else "",
    }


def _checker_probe(
    config: SupervisorConfig,
    *,
    label: str,
    script_name: str,
    extra_args: Sequence[str] = (),
) -> dict[str, Any]:
    return _command_result(
        label=label,
        command=[
            sys.executable,
            str(config.project_root / "scripts" / script_name),
            "--data-root",
            str(config.data_root),
            "--as-of",
            config.signal_date,
            *extra_args,
        ],
        cwd=config.project_root,
        timeout=180,
    )


def _daily_artifact_probe(config: SupervisorConfig) -> dict[str, Any]:
    return _checker_probe(
        config,
        label="daily_watch20.artifact",
        script_name="check_daily_watch20_producer_freshness.py",
        extra_args=("--artifact-only",),
    )


def _daily_producer_probe(config: SupervisorConfig) -> dict[str, Any]:
    return _checker_probe(
        config,
        label="daily_watch20.producer",
        script_name="check_daily_watch20_producer_freshness.py",
        extra_args=("--producer-only",),
    )


def _daily_delivery_probe(config: SupervisorConfig) -> dict[str, Any]:
    return _checker_probe(
        config,
        label="daily_watch20.delivery",
        script_name="check_daily_watch20_producer_freshness.py",
        extra_args=("--artifact-only", "--require-delivery"),
    )


def _d11_h5_delivery_probe(config: SupervisorConfig, source_date: str) -> dict[str, Any]:
    return _command_result(
        label="d11_h5_shadow.delivery",
        command=[
            sys.executable,
            "-m",
            "a_share_daily.d11_h5_shadow_delivery",
            "--source-date",
            source_date,
            "--signal-date",
            config.signal_date,
            "--check-only",
        ],
        cwd=config.project_root,
        timeout=180,
    )


def _daily_producer_recovery(config: SupervisorConfig) -> dict[str, Any]:
    timeout = float(os.environ.get("MORNING_SUPERVISOR_DW20_PRODUCER_TIMEOUT", "1800"))
    reset = _command_result(
        label="daily_watch20.producer.reset_failed",
        command=[
            "systemctl",
            "--user",
            "reset-failed",
            "daily-watch20-producer.service",
        ],
        cwd=config.project_root,
        timeout=30,
    )
    start_env = os.environ.copy()
    start_env.update(
        {
            "MARKET_INTEL_ROOT": str(config.project_root),
            "DATA_PLATFORM_ROOT": str(config.data_root),
            "WATCHLIST20_SOURCE_DATE": _latest_data_lake_trade_date(config.data_root) or "",
        }
    )
    start = _command_result(
        label="daily_watch20.producer.start",
        command=[
            "systemctl",
            "--user",
            "start",
            "daily-watch20-producer.service",
        ],
        cwd=config.project_root,
        env=start_env,
        timeout=timeout,
    )
    return {"ok": bool(reset["ok"] and start["ok"]), "steps": [reset, start]}


def _daily_delivery_recovery(config: SupervisorConfig, source_date: str) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "MARKET_INTEL_ROOT": str(config.project_root),
            "DATA_PLATFORM_ROOT": str(config.data_root),
            "TRADE_DATE": source_date,
            "SIGNAL_DATE": config.signal_date,
            "RUN_RESEARCH": "0",
        }
    )
    return _command_result(
        label="daily_watch20.delivery.retry",
        command=["bash", str(config.project_root / "scripts/daily_watch20_delivery.sh")],
        cwd=config.project_root,
        env=env,
        timeout=float(os.environ.get("MORNING_SUPERVISOR_DW20_DELIVERY_TIMEOUT", "600")),
    )


def _d11_h5_delivery_recovery(config: SupervisorConfig, source_date: str) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "MARKET_INTEL_ROOT": str(config.project_root),
            "DATA_PLATFORM_ROOT": str(config.data_root),
        }
    )
    return _command_result(
        label="d11_h5_shadow.delivery.retry",
        command=[
            sys.executable,
            "-m",
            "a_share_daily.d11_h5_shadow_delivery",
            "--source-date",
            source_date,
            "--signal-date",
            config.signal_date,
        ],
        cwd=config.project_root,
        env=env,
        timeout=float(os.environ.get("MORNING_SUPERVISOR_D11_H5_TIMEOUT", "1200")),
    )


def _run_stage(
    *,
    probe: Probe,
    recovery: Recovery,
    config: SupervisorConfig,
) -> dict[str, Any]:
    initial = probe()
    result: dict[str, Any] = {
        "status": "healthy" if initial["ok"] else "failed",
        "initial_probe": initial,
        "recovery_attempts": [],
        "final_probe": initial,
    }
    if initial["ok"] or not config.recover:
        return result

    attempts: list[dict[str, Any]] = result["recovery_attempts"]
    for attempt_number in range(1, config.max_recovery_attempts + 1):
        recovery_result = recovery()
        final_probe = probe()
        attempts.append(
            {
                "attempt": attempt_number,
                "recovery": recovery_result,
                "probe": final_probe,
            }
        )
        result["final_probe"] = final_probe
        if final_probe["ok"]:
            result["status"] = "recovered"
            return result
        if config.retry_delay_seconds > 0 and attempt_number < config.max_recovery_attempts:
            time.sleep(config.retry_delay_seconds)
    return result


def _product_summary_line(label: str, stages: Mapping[str, Any]) -> str:
    stage_text = "，".join(
        f"{name}={value.get('status', 'unknown')}"
        for name, value in stages.items()
        if isinstance(value, Mapping)
    )
    return f"- {label}：{stage_text or 'not_due'}"


def _summary_markdown(payload: Mapping[str, Any]) -> str:
    products = payload.get("products")
    product_map = products if isinstance(products, Mapping) else {}
    if not payload.get("success"):
        heading = "⚠️ **晨报 supervisor 恢复失败**"
    elif _has_recovery(payload):
        heading = "✅ **晨报 supervisor 自动恢复完成**"
    else:
        heading = "✅ **晨报 supervisor 检查通过**"
    return "\n".join(
        [
            heading,
            "",
            (
                f"source={payload.get('source_date', 'unknown')} "
                f"signal={payload.get('signal_date', 'unknown')} "
                f"phase={payload.get('phase', 'unknown')}"
            ),
            "",
            _product_summary_line(
                "DailyWatch20",
                product_map.get("daily_watch20", {})
                if isinstance(product_map.get("daily_watch20"), Mapping)
                else {},
            ),
            _product_summary_line(
                "D11-H5 研究影子",
                product_map.get("d11_h5_shadow", {})
                if isinstance(product_map.get("d11_h5_shadow"), Mapping)
                else {},
            ),
            "",
            f"> {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')} 检查",
        ]
    )


def _send_summary(payload: Mapping[str, Any]) -> bool:
    chat_id = (
        os.environ.get("WATCHDOG_ALERT_FEISHU_CHAT_ID", "").strip()
        or os.environ.get("A_SHARE_FEISHU_DM_CHAT_ID", "").strip()
    )
    if not chat_id:
        print("[morning-supervisor] alert chat id is not configured", file=sys.stderr)
        return False
    lark_cli = os.environ.get("LARK_CLI", str(Path.home() / ".local/bin/lark-cli"))
    if not Path(lark_cli).is_file():
        print(f"[morning-supervisor] lark-cli not found: {lark_cli}", file=sys.stderr)
        return False
    markdown = _summary_markdown(payload)
    key_material = "\0".join(
        (
            str(payload.get("signal_date")),
            str(payload.get("phase")),
            str(payload.get("success")),
            markdown,
        )
    )
    idempotency_key = "morning-supervisor-" + hashlib.sha256(key_material.encode()).hexdigest()[:24]
    result = subprocess.run(
        [
            lark_cli,
            "im",
            "+messages-send",
            "--chat-id",
            chat_id,
            "--markdown",
            markdown,
            "--idempotency-key",
            idempotency_key,
            "--as",
            "bot",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode != 0:
        # Surface the hard failure reason so run() can tell a credential/bot
        # failure apart from a transient one. Keep returning bool by contract.
        reason = result.stderr.strip() or f"lark-cli exited with code {result.returncode}"
        print(
            f"[morning-supervisor] ALERT SEND FAILED (returncode={result.returncode}): {reason}",
            file=sys.stderr,
        )
        return False
    # Enhancement 3: treat "send succeeded" as "lark-cli returned 0 AND the bot
    # credential is provably live". lark-cli may return 0 while the message is
    # silently dropped (stale/invalid token, bot unbound). We verify reachability
    # with a lightweight `lark-cli whoami` subprocess — no hermes/heavy deps.
    if not _lark_reachability_ok(lark_cli):
        print(
            "[morning-supervisor] ALERT SEND RETURNED 0 but reachability probe "
            "(lark-cli whoami) failed; treating as undelivered",
            file=sys.stderr,
        )
        return False
    return True


def _lark_reachability_ok(lark_cli: str) -> bool:
    """Lightweight reachability probe: bot credential live via `lark-cli whoami`.

    Mirrors ``delivery.senders._lark_whoami_ready`` but without pulling in the
    heavier senders module (which can trigger hermes binding). Returns True only
    when the bot identity is reported available with a ready token.
    """
    try:
        probe = subprocess.run(
            [lark_cli, "whoami"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[morning-supervisor] reachability probe error: {exc}", file=sys.stderr)
        return False
    if probe.returncode != 0:
        stderr = (probe.stderr or probe.stdout or "").strip()
        print(
            f"[morning-supervisor] reachability probe whoami returned "
            f"{probe.returncode}: {stderr[:300]}",
            file=sys.stderr,
        )
        return False
    try:
        payload = json.loads(probe.stdout)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        return False
    ready = (
        payload.get("identity") == "bot"
        and payload.get("available") is True
        and payload.get("tokenStatus") == "ready"
    )
    if not ready:
        print(
            f"[morning-supervisor] reachability probe not ready: "
            f"identity={payload.get('identity')} available={payload.get('available')} "
            f"tokenStatus={payload.get('tokenStatus')}",
            file=sys.stderr,
        )
    return ready


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
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


def _write_state(config: SupervisorConfig, phase_payload: Mapping[str, Any]) -> Path:
    state_path = config.state_root / f"{config.signal_date}.json"
    existing: dict[str, Any] = {}
    if state_path.is_file():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict) and loaded.get("signal_date") == config.signal_date:
            existing = loaded
    phases = existing.get("phases")
    if not isinstance(phases, dict):
        phases = {}
    phases[config.phase] = dict(phase_payload)
    payload = {
        "schema_version": "morning_report_supervisor.v1",
        "signal_date": config.signal_date,
        "source_date": phase_payload.get("source_date"),
        "updated_at": datetime.now(UTC).isoformat(),
        "phases": phases,
    }
    _atomic_write_json(state_path, payload)
    _atomic_write_json(config.state_root / "latest.json", payload)
    return state_path


def _record_alert_failure(config: SupervisorConfig, state_path: Path) -> None:
    """Persist that the watchdog's own alert failed to send.

    Writes a standalone marker file and patches alert_status into the existing
    state JSON so a failed escalation is visible even if nobody reads logs.
    """
    ts = datetime.now(UTC).isoformat()
    marker = config.state_root / f"alert_failed.{config.signal_date}"
    try:
        marker.write_text(
            json.dumps(
                {
                    "schema_version": "morning_report_supervisor.alert_failed.v1",
                    "signal_date": config.signal_date,
                    "phase": config.phase,
                    "failed_at": ts,
                    "reason": "lark-cli alert send returned False (credential/bot failure)",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:  # never let the marker writer mask the real failure
        print(f"[morning-supervisor] could not write alert_failed marker: {exc}", file=sys.stderr)
    # Patch alert_status into the existing per-date + latest state JSON.
    for path in (state_path, config.state_root / "latest.json"):
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        doc["alert_status"] = "failed"
        doc["alert_failed_at"] = ts
        _atomic_write_json(path, doc)


def _has_recovery(payload: Mapping[str, Any]) -> bool:
    products = payload.get("products")
    if not isinstance(products, Mapping):
        return False
    for product in products.values():
        if not isinstance(product, Mapping):
            continue
        for stage in product.values():
            if isinstance(stage, Mapping) and stage.get("recovery_attempts"):
                return True
    return False


def supervise(config: SupervisorConfig) -> tuple[int, dict[str, Any]]:
    started_at = datetime.now(UTC).isoformat()
    calendar_path = _trade_calendar_path(config.data_root)
    if not _env_truthy("MORNING_ALLOW_NON_TRADING_DAY"):
        try:
            if not is_open_trading_day(calendar_path, config.signal_date):
                payload = {
                    "phase": config.phase,
                    "signal_date": config.signal_date,
                    "source_date": None,
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "status": "skipped_non_trading_day",
                    "success": True,
                    "products": {},
                }
                return 0, payload
        except TradingCalendarError as exc:
            payload = {
                "phase": config.phase,
                "signal_date": config.signal_date,
                "source_date": None,
                "started_at": started_at,
                "finished_at": datetime.now(UTC).isoformat(),
                "status": "calendar_error",
                "success": False,
                "error": str(exc),
                "products": {},
            }
            return 1, payload

    source_date = _latest_data_lake_trade_date(config.data_root)
    if source_date is None:
        payload = {
            "phase": config.phase,
            "signal_date": config.signal_date,
            "source_date": None,
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "status": "source_date_unavailable",
            "success": False,
            "products": {},
        }
        return 1, payload

    daily_stages: dict[str, Any] = {}
    daily_stages["producer"] = _run_stage(
        probe=lambda: _daily_producer_probe(config),
        recovery=lambda: _daily_producer_recovery(config),
        config=config,
    )
    daily_stages["artifact"] = _run_stage(
        probe=lambda: _daily_artifact_probe(config),
        recovery=lambda: _daily_producer_recovery(config),
        config=config,
    )
    products: dict[str, Any] = {
        "daily_watch20": daily_stages,
        "d11_h5_shadow": {},
    }
    if config.phase == "postflight" and daily_stages["artifact"]["final_probe"]["ok"]:
        daily_stages["delivery"] = _run_stage(
            probe=lambda: _daily_delivery_probe(config),
            recovery=lambda: _daily_delivery_recovery(config, source_date),
            config=config,
        )
    if config.phase == "postflight":
        products["d11_h5_shadow"]["delivery"] = _run_stage(
            probe=lambda: _d11_h5_delivery_probe(config, source_date),
            recovery=lambda: _d11_h5_delivery_recovery(config, source_date),
            config=config,
        )

    stages = [
        stage
        for product in products.values()
        for stage in product.values()
        if isinstance(stage, Mapping)
    ]
    success = bool(stages) and all(
        isinstance(stage.get("final_probe"), Mapping) and bool(stage["final_probe"].get("ok"))
        for stage in stages
    )
    payload = {
        "phase": config.phase,
        "signal_date": config.signal_date,
        "source_date": source_date,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "status": "complete" if success else "failed",
        "success": success,
        "products": products,
    }
    return (0 if success else 1), payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Self-heal and verify DailyWatch20 plus D11-H5 research shadow"
    )
    parser.add_argument("--phase", choices=("preflight", "postflight"), required=True)
    parser.add_argument("--as-of", help="Signal date YYYYMMDD (default: today)")
    parser.add_argument("--project-root", type=Path, default=_default_project_root())
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument(
        "--max-recovery-attempts",
        type=int,
        default=int(os.environ.get("MORNING_SUPERVISOR_MAX_RECOVERY_ATTEMPTS", "2")),
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=float(os.environ.get("MORNING_SUPERVISOR_RETRY_DELAY_SECONDS", "15")),
    )
    parser.add_argument("--no-recover", action="store_true")
    parser.add_argument("--notify", action="store_true")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    signal_date = (
        datetime.strptime(args.as_of, "%Y%m%d").strftime("%Y%m%d")
        if args.as_of
        else date.today().strftime("%Y%m%d")
    )
    if args.max_recovery_attempts < 1:
        raise SystemExit("--max-recovery-attempts must be at least 1")
    if args.retry_delay_seconds < 0:
        raise SystemExit("--retry-delay-seconds must be non-negative")
    project_root = args.project_root.expanduser().resolve()
    state_root = (
        args.state_root.expanduser().resolve()
        if args.state_root
        else _default_state_root(project_root).resolve()
    )
    config = SupervisorConfig(
        project_root=project_root,
        data_root=(args.data_root or _default_data_root()).expanduser().resolve(),
        state_root=state_root,
        phase=args.phase,
        signal_date=signal_date,
        max_recovery_attempts=args.max_recovery_attempts,
        retry_delay_seconds=args.retry_delay_seconds,
        recover=not args.no_recover,
        notify=args.notify,
    )
    state_root.mkdir(parents=True, exist_ok=True)
    lock_path = state_root / ".lock"
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[morning-supervisor] another run is active", file=sys.stderr)
            return 3
        status, payload = supervise(config)
        state_path = _write_state(config, payload)
        print(_summary_markdown(payload))
        print(f"supervisor_state={state_path}")
        send_failed = False
        if config.notify and (not payload.get("success") or _has_recovery(payload)):
            alert_ok = _send_summary(payload)
            if not alert_ok:
                send_failed = True
                _record_alert_failure(config, state_path)
        if send_failed:
            # Do not silently swallow a failed alert: make the process exit
            # non-zero so systemd marks the unit failed and the freshness
            # watchdog can escalate independently.
            print(
                "[morning-supervisor] CRITICAL: alert failed to send; exiting non-zero",
                file=sys.stderr,
            )
            return 4
        return status


if __name__ == "__main__":
    raise SystemExit(run())
