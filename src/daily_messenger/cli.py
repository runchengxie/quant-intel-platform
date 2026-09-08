from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from daily_messenger.common.logging import log, setup_logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_runtime_env_files() -> None:
    """Load project .env files before importing modules with env-sensitive globals."""
    for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ[key] = value


@contextmanager
def _env_override(key: str, value: str | None) -> Iterator[None]:
    original = os.environ.get(key)
    if value is None:
        yield
        return
    os.environ[key] = value
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


def _ensure_run_id() -> None:
    os.environ.setdefault("DM_RUN_ID", uuid.uuid4().hex)


def _execute_step(name: str, func, args: list[str] | None, logger: logging.Logger) -> int:
    log(logger, logging.INFO, "cli_step_start", step=name, argv=args or [])
    code = func(args)
    level = logging.INFO if code == 0 else logging.ERROR
    log(logger, level, "cli_step_complete", step=name, exit_code=code)
    return code


def _add_run_parser(subparsers: argparse._SubParsersAction) -> None:
    run_parser = subparsers.add_parser("run", help="Run ETL, scoring, and digest sequentially")
    run_parser.add_argument("--date", help="Override trading day (YYYY-MM-DD)")
    run_parser.add_argument("--force-fetch", action="store_true", help="Force refresh ETL step")
    run_parser.add_argument(
        "--force-score", action="store_true", help="Force recompute scoring step"
    )
    run_parser.add_argument(
        "--degraded", action="store_true", help="Render digest in degraded mode"
    )
    run_parser.add_argument(
        "--strict", action="store_true", help="Enable STRICT mode during scoring"
    )
    run_parser.add_argument(
        "--disable-throttle",
        action="store_true",
        help="Disable network throttling helpers",
    )


def _add_fetch_parser(subparsers: argparse._SubParsersAction) -> None:
    fetch_parser = subparsers.add_parser("fetch", help="Run ETL only")
    fetch_parser.add_argument("--date", help="Override trading day (YYYY-MM-DD)")
    fetch_parser.add_argument("--force", action="store_true", help="Force refresh ETL step")
    fetch_parser.add_argument(
        "--disable-throttle",
        action="store_true",
        help="Disable network throttling helpers",
    )


def _add_score_parser(subparsers: argparse._SubParsersAction) -> None:
    score_parser = subparsers.add_parser("score", help="Run scoring only")
    score_parser.add_argument("--date", help="Override trading day (YYYY-MM-DD)")
    score_parser.add_argument("--force", action="store_true", help="Force recompute scoring")
    score_parser.add_argument("--strict", action="store_true", help="Enable STRICT mode")


def _add_digest_parser(subparsers: argparse._SubParsersAction) -> None:
    digest_parser = subparsers.add_parser("digest", help="Render digest only")
    digest_parser.add_argument("--date", help="Override trading day (YYYY-MM-DD)")
    digest_parser.add_argument("--degraded", action="store_true", help="Render in degraded mode")


def _add_dashboard_parser(subparsers: argparse._SubParsersAction, web_dashboard: object) -> None:
    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Build static market intelligence dashboard"
    )
    dashboard_out = web_dashboard.OUT_DIR / "web_dashboard.html"  # ty: ignore[unresolved-attribute]
    dashboard_parser.add_argument(
        "--out",
        default=str(dashboard_out),
        help="Output HTML path (default: out/web_dashboard.html)",
    )
    dashboard_parser.add_argument(
        "--state-panel",
        help="Optional CSV with market-state proxy columns",
    )
    dashboard_parser.add_argument(
        "--snapshot-dir",
        default=str(web_dashboard.SNAPSHOT_DIR),  # ty: ignore[unresolved-attribute]
        help="Directory containing latest snapshot JSON files",
    )
    dashboard_parser.add_argument(
        "--no-payload-json",
        action="store_true",
        help="Do not write web_dashboard_payload.json next to the HTML file",
    )


def _add_state_panel_parser(subparsers: argparse._SubParsersAction, state_panel) -> None:
    state_panel_parser = subparsers.add_parser(
        "state-panel", help="Build dashboard market-state panel from public sources"
    )
    state_panel_parser.add_argument(
        "--out",
        default=str(state_panel.DEFAULT_OUTPUT),
        help="Output CSV path (default: out/market_state_panel.csv)",
    )
    state_panel_parser.add_argument(
        "--period",
        default=state_panel.DEFAULT_PERIOD,
        help=f"yfinance lookback period when --start is not set (default: {state_panel.DEFAULT_PERIOD})",
    )
    state_panel_parser.add_argument(
        "--start", help="Start date for historical sources (YYYY-MM-DD)"
    )
    state_panel_parser.add_argument(
        "--include-breadth",
        action="store_true",
        help="Also fit SPX/NDX 20/50/200D breadth",
    )
    state_panel_parser.add_argument(
        "--breadth-mode",
        choices=("sample", "full"),
        default=state_panel.DEFAULT_BREADTH_MODE,
        help="Use core sample constituents or full current public constituents (default: sample)",
    )
    state_panel_parser.add_argument(
        "--timeout",
        type=int,
        default=state_panel.DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {state_panel.DEFAULT_TIMEOUT})",
    )
    state_panel_parser.add_argument(
        "--min-rows",
        type=int,
        default=30,
        help="Fail when fewer effective rows are produced (default: 30)",
    )


def _add_btc_parser(subparsers: argparse._SubParsersAction) -> None:
    from daily_messenger.crypto import klines as btc_klines
    from daily_messenger.crypto import report as btc_report

    btc_parser = subparsers.add_parser("btc", help="BTC monitoring helpers")
    btc_sub = btc_parser.add_subparsers(dest="btc_command", required=True)

    btc_init_parser = btc_sub.add_parser(
        "init-history", help="一次性下载 Binance 日度压缩包并合并为 Parquet"
    )
    btc_init_parser.add_argument("--symbol", default="BTCUSDT")
    btc_init_parser.add_argument("--interval", default="1m", choices=sorted(btc_klines.INTERVALS))
    btc_init_parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    btc_init_parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    btc_init_parser.add_argument(
        "--outdir",
        default=str(btc_klines.DEFAULT_DATA_DIR),
        help="输出目录（默认 out/btc）",
    )

    btc_fetch_parser = btc_sub.add_parser(
        "fetch", help="增量刷新 Binance/Kraken/Bitstamp K 线并写入 Parquet"
    )
    btc_fetch_parser.add_argument(
        "--interval", default="1m", choices=sorted(btc_klines.INTERVAL_MAP)
    )
    btc_fetch_parser.add_argument("--symbol", default="BTCUSDT")
    btc_fetch_parser.add_argument(
        "--outdir",
        default=str(btc_klines.DEFAULT_DATA_DIR),
        help="输出目录（默认 out/btc）",
    )
    btc_fetch_parser.add_argument("--lookback", default="2d", help="回看窗口，如 7d/3h/1d")
    btc_fetch_parser.add_argument("--max-pages", type=int, default=100)

    btc_report_parser = btc_sub.add_parser("report", help="生成 BTC Markdown 日报")
    btc_report_parser.add_argument(
        "--datadir",
        default=str(btc_report.DEFAULT_DATA_DIR),
        help="Parquet 数据目录（默认 out/btc）",
    )
    btc_report_parser.add_argument(
        "--out",
        default=str(btc_report.DEFAULT_REPORT),
        help="输出 Markdown 文件（默认 out/btc_report.md）",
    )
    btc_report_parser.add_argument(
        "--config",
        default=str(btc_report.DEFAULT_CONFIG),
        help="技术分析配置（默认 config/ta_btc.yml）",
    )


def _add_style_replica_parser(subparsers: argparse._SubParsersAction) -> None:
    # ── StyleReplica-A80B20-v0 push ──────────────────────────────────────────
    sr_parser = subparsers.add_parser(
        "style-replica",
        help="Generate the internal-only legacy StyleReplica report",
    )
    sr_parser.add_argument("--positions", help="Path to positions CSV")
    sr_parser.add_argument("--date", help="Signal date YYYYMMDD (default: today)")
    sr_parser.add_argument(
        "--user-id",
        help="Internal Feishu open_id; must match STYLE_REPLICA_INTERNAL_FEISHU_USER_ID",
    )
    sr_parser.add_argument("--dry-run", action="store_true", help="Print instead of sending")
    sr_parser.add_argument(
        "--internal-only",
        action="store_true",
        help="Acknowledge that this legacy report may only go to the internal allowlist",
    )


def _build_parser() -> argparse.ArgumentParser:
    """Construct the ``dm`` CLI parser with all subcommands.

    Delayed imports of heavy pipeline modules live in the per-subcommand
    helpers (not at module top) so the CLI does not pay their import cost
    unless a subcommand needs them.
    """
    from daily_messenger.dashboard import state_panel, web_dashboard

    parser = argparse.ArgumentParser(prog="dm", description="Daily Messenger CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_run_parser(subparsers)
    _add_fetch_parser(subparsers)
    _add_score_parser(subparsers)
    _add_digest_parser(subparsers)
    _add_dashboard_parser(subparsers, web_dashboard)
    _add_state_panel_parser(subparsers, state_panel)
    _add_btc_parser(subparsers)
    _add_style_replica_parser(subparsers)

    return parser


def _run_btc_subcommand(args: argparse.Namespace) -> int:
    from daily_messenger.crypto import klines as btc_klines
    from daily_messenger.crypto import report as btc_report

    if args.btc_command == "init-history":
        btc_klines.init_history(
            symbol=args.symbol,
            interval=args.interval,
            start=datetime.fromisoformat(args.start).replace(tzinfo=UTC),
            end=datetime.fromisoformat(args.end).replace(tzinfo=UTC),
            outdir=Path(args.outdir),
        )
        return 0
    if args.btc_command == "fetch":
        btc_klines.incremental_fetch(
            interval=args.interval,
            symbol=args.symbol,
            outdir=Path(args.outdir),
            lookback=args.lookback,
            max_pages=args.max_pages,
        )
        return 0
    if args.btc_command == "report":
        btc_report.build_report(
            datadir=Path(args.datadir),
            outpath=Path(args.out),
            config_path=Path(args.config) if args.config else None,
        )
        return 0
    raise ValueError(f"Unknown btc sub-command {args.btc_command}")


def _run_pipeline(args: argparse.Namespace, logger: logging.Logger) -> int:
    from daily_messenger.digest import make_daily
    from daily_messenger.etl import run_fetch
    from daily_messenger.scoring import run_scores

    exit_code = 0
    with _env_override("DM_OVERRIDE_DATE", args.date):
        fetch_args = ["--force"] if args.force_fetch else []
        exit_code = _execute_step("etl", run_fetch.run, fetch_args, logger)
        if exit_code != 0:
            return exit_code

        score_args = ["--force"] if args.force_score else []
        with _env_override("STRICT", "1" if args.strict else None):
            exit_code = _execute_step("scoring", run_scores.run, score_args, logger)
        if exit_code != 0:
            return exit_code

        digest_args: list[str] = []
        if args.degraded:
            digest_args.append("--degraded")
        return _execute_step("digest", make_daily.run, digest_args, logger)


def _dispatch_style_replica(args: argparse.Namespace) -> int:
    from style_replica_bridge import push_daily_holdings

    user_id = getattr(args, "user_id", None) or os.environ.get(
        "STYLE_REPLICA_INTERNAL_FEISHU_USER_ID", ""
    )
    positions_path = getattr(
        args, "positions", None
    ) or "out/style_replica/{}/positions.csv".format(
        (getattr(args, "date", None) or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    )
    ok = push_daily_holdings(
        positions_path,
        signal_date=getattr(args, "date", "").replace("-", "") or None,
        user_id=user_id or None,
        dry_run=getattr(args, "dry_run", False),
        internal_delivery=getattr(args, "internal_only", False),
    )
    return 0 if ok else 1


def _dispatch_fetch(args: argparse.Namespace, logger: logging.Logger) -> int:
    from daily_messenger.etl import run_fetch

    with _env_override("DM_OVERRIDE_DATE", args.date):
        return _execute_step(
            "etl",
            run_fetch.run,
            ["--force"] if args.force else [],
            logger,
        )


def _dispatch_score(args: argparse.Namespace, logger: logging.Logger) -> int:
    from daily_messenger.scoring import run_scores

    with (
        _env_override("DM_OVERRIDE_DATE", args.date),
        _env_override("STRICT", "1" if args.strict else None),
    ):
        step_args = ["--force"] if args.force else []
        return _execute_step("scoring", run_scores.run, step_args, logger)


def _dispatch_digest(args: argparse.Namespace, logger: logging.Logger) -> int:
    from daily_messenger.digest import make_daily

    with _env_override("DM_OVERRIDE_DATE", args.date):
        digest_step_args: list[str] = []
        if args.degraded:
            digest_step_args.append("--degraded")
        return _execute_step("digest", make_daily.run, digest_step_args, logger)


def _dispatch_dashboard(args: argparse.Namespace, logger: logging.Logger) -> int:
    from daily_messenger.dashboard import web_dashboard

    dashboard_args = ["--out", args.out, "--snapshot-dir", args.snapshot_dir]
    if args.state_panel:
        dashboard_args.extend(["--state-panel", args.state_panel])
    if args.no_payload_json:
        dashboard_args.append("--no-payload-json")
    return _execute_step("dashboard", web_dashboard.run, dashboard_args, logger)


def _dispatch_state_panel(args: argparse.Namespace, logger: logging.Logger) -> int:
    from daily_messenger.dashboard import state_panel

    state_panel_args = [
        "--out",
        args.out,
        "--period",
        args.period,
        "--timeout",
        str(args.timeout),
        "--min-rows",
        str(args.min_rows),
    ]
    if args.start:
        state_panel_args.extend(["--start", args.start])
    if args.include_breadth:
        state_panel_args.append("--include-breadth")
        state_panel_args.extend(["--breadth-mode", args.breadth_mode])
    return _execute_step("state_panel", state_panel.run, state_panel_args, logger)


def _dispatch(args: argparse.Namespace, logger: logging.Logger) -> int:
    if getattr(args, "disable_throttle", False):
        os.environ["DM_DISABLE_THROTTLE"] = "1"

    if args.command == "style-replica":
        return _dispatch_style_replica(args)

    if args.command == "fetch":
        return _dispatch_fetch(args, logger)

    if args.command == "score":
        return _dispatch_score(args, logger)

    if args.command == "digest":
        return _dispatch_digest(args, logger)

    if args.command == "dashboard":
        return _dispatch_dashboard(args, logger)

    if args.command == "state-panel":
        return _dispatch_state_panel(args, logger)

    if args.command == "btc":
        return _run_btc_subcommand(args)

    return _run_pipeline(args, logger)


def main(argv: list[str] | None = None) -> int:
    _load_runtime_env_files()
    _ensure_run_id()

    args = _build_parser().parse_args(argv)
    logger = setup_logger("cli", command=args.command)
    return _dispatch(args, logger)


if __name__ == "__main__":
    sys.exit(main())
