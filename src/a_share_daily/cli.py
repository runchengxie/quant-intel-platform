"""CLI entry for the A-share daily report pipeline.

Usage:
    uv run a-share-daily morning [--date YYYYMMDD]
    uv run a-share-daily morning-report [--manifest PATH] [--news PATH] [--out PATH]
    uv run a-share-daily daily-watch20 [--source-date YYYYMMDD] [--dry-run]
    uv run a-share-daily weekly-basket --as-of-date YYYYMMDD --dailywatch PATH
        --cashflow PATH --cashflow-receipt PATH --output-root PATH [--send]
    uv run a-share-daily cashflow-delivery --selection PATH --source-date YYYYMMDD --signal-date YYYYMMDD --chat-id CHAT
    uv run a-share-daily cashflow-status-notify --status-json PATH --receipt PATH --chat-id CHAT [--send]
    uv run a-share-daily cashflow-portfolio-render --selection PATH --chart-out PATH
    uv run a-share-daily evening [--date YYYYMMDD] [--json] [--send-feishu]
    uv run a-share-daily review  [--date YYYYMMDD] [--json] [--send-feishu]
    uv run a-share-daily doctor  [--live] [--strict]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(Exception):
            reconfigure(encoding="utf-8")


def _default_feishu_chat_id() -> str:
    return (
        os.environ.get("MARKET_INTEL_INTERNAL_CHAT_ID")
        or os.environ.get("MARKET_INTEL_CLIENT_CHAT_ID")
        or ""
    )


def _require_feishu_chat_id(chat_id: str) -> str:
    chat_id = chat_id.strip()
    if chat_id:
        return chat_id
    print(
        "[FAIL] set MARKET_INTEL_INTERNAL_CHAT_ID or pass --feishu-chat-id",
        file=sys.stderr,
    )
    sys.exit(1)


def _send_to_feishu(markdown: str, chat_id: str) -> bool:
    """Send markdown text to a Feishu group via lark-cli."""
    lark_cli = os.environ.get("LARK_CLI", str(Path.home() / ".local" / "bin" / "lark-cli"))
    try:
        result = subprocess.run(
            [
                lark_cli,
                "im",
                "+messages-send",
                "--as",
                "bot",
                "--chat-id",
                chat_id,
                "--markdown",
                markdown,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"[FAIL] lark-cli: {result.stderr[:500]}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"[FAIL] lark-cli: {e}", file=sys.stderr)
        return False


def _add_morning_commands(sub: argparse._SubParsersAction) -> None:
    morning = sub.add_parser("morning", help="Run mechanical pipeline, output manifest JSON")
    morning.add_argument("--date", help="Trade date YYYYMMDD")

    report = sub.add_parser("morning-report", help="Render deterministic morning Markdown report")
    report.add_argument(
        "--manifest",
        default="out/a_share_daily/morning_manifest.json",
        help="Morning manifest JSON from `a-share-daily morning`",
    )
    report.add_argument(
        "--news",
        default="out/a_share_daily/ai_market_news.json",
        help="Structured market-news JSON",
    )
    report.add_argument(
        "--out",
        default="out/a_share_daily/morning_report.md",
        help="Output Markdown path",
    )
    report.add_argument("--send-feishu", action="store_true", help="Send report to Feishu")
    report.add_argument(
        "--feishu-chat-id",
        default=_default_feishu_chat_id(),
        help="Feishu chat ID",
    )


def _add_watch_command(sub: argparse._SubParsersAction) -> None:
    watch = sub.add_parser(
        "daily-watch20",
        help="Validate and render the published DailyWatch20 artifact",
    )
    watch.add_argument(
        "--root",
        help="Artifact root (default: WATCHLIST20_ROOT or platform strategy_outputs latest)",
    )
    watch.add_argument("--source-date", help="Required source date for freshness, YYYYMMDD")
    watch.add_argument("--signal-date", help="Optional required signal date, YYYYMMDD")
    watch.add_argument(
        "--audience",
        choices=("client", "internal"),
        default="client",
        help="Render a client-safe report or the full internal audit report",
    )
    watch.add_argument(
        "--out-dir",
        default="out/a_share_daily/daily_watch20",
        help="Output parent directory for HTML and PNG",
    )
    watch.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the receipt summary without writing files",
    )


def _add_cashflow_commands(sub: argparse._SubParsersAction) -> None:
    cashflow = sub.add_parser(
        "cashflow-delivery",
        help="Deliver a validated cashflow research artifact to explicit Feishu test chats",
    )
    cashflow.add_argument("--selection", required=True, help="Cashflow selection.json")
    cashflow.add_argument("--source-date", required=True, help="Source date YYYYMMDD")
    cashflow.add_argument("--signal-date", required=True, help="Signal date YYYYMMDD")
    cashflow.add_argument(
        "--publication-receipt", required=True, help="Passed cashflow publication receipt"
    )
    cashflow.add_argument("--receipt", required=True, help="Delivery receipt output path")
    cashflow.add_argument(
        "--chat-id", action="append", required=True, help="Explicit Feishu chat ID"
    )
    cashflow.add_argument(
        "--artifact-kind",
        choices=("selection", "executable"),
        default="selection",
        help="Artifact contract to validate before delivery",
    )
    cashflow.add_argument(
        "--lark-cli",
        default=os.environ.get("LARK_CLI", str(Path.home() / ".local" / "bin" / "lark-cli")),
    )
    cashflow.add_argument("--dry-run", action="store_true")

    status = sub.add_parser(
        "cashflow-status-notify",
        help="Send blocked/shadow/dry-run status to explicit Feishu test chats",
    )
    status.add_argument("--status-json", required=True, help="Status-only input JSON")
    status.add_argument("--receipt", required=True, help="Status delivery receipt output path")
    status.add_argument("--chat-id", action="append", required=True, help="Explicit Feishu chat ID")
    status.add_argument(
        "--lark-cli",
        default=os.environ.get("LARK_CLI", str(Path.home() / ".local" / "bin" / "lark-cli")),
    )
    status.add_argument("--send", action="store_true", help="Actually send instead of dry-run")
    status.add_argument("--send-confirmation")

    portfolio = sub.add_parser(
        "cashflow-portfolio-render",
        help="Render a passed cashflow selection as a research portfolio chart",
    )
    portfolio.add_argument("--selection", required=True, help="Cashflow selection.json")
    portfolio.add_argument("--chart-out", required=True, help="PNG output path")
    portfolio.add_argument(
        "--instruments",
        help="Optional symbol/name snapshot parquet used to pin company names",
    )


def _add_weekly_basket_command(sub: argparse._SubParsersAction) -> None:
    basket = sub.add_parser(
        "weekly-basket",
        help="Compose a validated weekly ten-stock basket and optional personal Feishu report",
    )
    basket.add_argument("--as-of-date", required=True, help="Basket date YYYYMMDD")
    basket.add_argument("--dailywatch", required=True, help="DailyWatch20 or D11-H5 JSON artifact")
    basket.add_argument("--d11-h5", help="Optional D11-H5 artifact overriding --dailywatch")
    basket.add_argument("--cashflow", required=True, help="Cashflow selection JSON artifact")
    basket.add_argument(
        "--cashflow-receipt", required=True, help="Cashflow publication receipt JSON"
    )
    basket.add_argument("--microcap", help="Microcap shadow selection JSON artifact")
    basket.add_argument(
        "--microcap-quota",
        type=int,
        choices=(0, 2, 3),
        default=3,
        help="Microcap positions in V1; 0 uses a 7/3/0 DailyWatch/Cashflow split",
    )
    basket.add_argument("--previous", help="Previous canonical basket.json")
    basket.add_argument("--output-root", required=True, help="Weekly basket artifact root")
    basket.add_argument(
        "--send", action="store_true", help="Send only to the explicit personal app target"
    )
    basket.add_argument("--dry-run", action="store_true", help="Build artifacts without sending")
    basket.add_argument("--personal-chat-id", help="Explicit personal Feishu chat ID")
    basket.add_argument(
        "--lark-cli",
        default=os.environ.get("LARK_CLI", str(Path.home() / ".local" / "bin" / "lark-cli")),
    )


def _add_operational_commands(sub: argparse._SubParsersAction) -> None:
    doctor = sub.add_parser("doctor", help="Check A-share daily deployment")
    doctor.add_argument(
        "--live",
        action="store_true",
        help="Also check local systemd timers and Hermes cron state",
    )
    doctor.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when warnings are present",
    )

    for name in ("evening", "review"):
        command = sub.add_parser(name, help="Run post-market review")
        command.add_argument("--date", help="Trade date YYYYMMDD")
        command.add_argument("--json", action="store_true", help="JSON output")
        command.add_argument(
            "--send-feishu",
            action="store_true",
            help="Send output to Feishu group after generation",
        )
        command.add_argument(
            "--feishu-chat-id",
            default=_default_feishu_chat_id(),
            help="Feishu chat ID",
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A-share daily report pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_morning_commands(sub)
    _add_watch_command(sub)
    _add_cashflow_commands(sub)
    _add_weekly_basket_command(sub)
    _add_operational_commands(sub)
    return parser


def _maybe_send_feishu(output: str, args: argparse.Namespace) -> int | None:
    """Send ``output`` to Feishu when requested by the parsed args.

    Returns 1 on delivery failure, otherwise ``None`` (caller proceeds to exit 0).
    """
    if not getattr(args, "send_feishu", False):
        return None
    chat_id = _require_feishu_chat_id(getattr(args, "feishu_chat_id", ""))
    ok = _send_to_feishu(output, chat_id)
    if ok:
        print("[OK] Sent to Feishu", file=sys.stderr)
        return None
    print("[FAIL] Feishu delivery failed", file=sys.stderr)
    return 1


def _cmd_morning(args: argparse.Namespace) -> int | None:
    from .pipeline import run_morning

    manifest = run_morning(args.date)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return None


def _cmd_morning_report(args: argparse.Namespace) -> int | None:
    from .morning_report import load_json, render_morning_report, write_report

    manifest = load_json(args.manifest)
    news = load_json(args.news)
    output = render_morning_report(manifest, news)
    write_report(args.out, output)
    print(output)
    return _maybe_send_feishu(output, args)


def _cmd_daily_watch20(args: argparse.Namespace) -> int | None:
    from .daily_watch20 import artifact_summary, load_daily_watch20
    from .daily_watch20_render import render_daily_watch20

    artifact = load_daily_watch20(
        args.root,
        expected_source_date=args.source_date,
        expected_signal_date=args.signal_date,
        expected_candidate_pool_mode=("ths_hot_strict_v3" if args.audience == "client" else None),
    )
    payload = artifact_summary(artifact)
    if not args.dry_run:
        output_dir = Path(args.out_dir).expanduser() / artifact.signal_date
        rendered = render_daily_watch20(artifact, output_dir, audience=args.audience)
        payload["html_path"] = str(rendered.html_path)
        payload["png_path"] = str(rendered.png_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return None


def _cmd_doctor(args: argparse.Namespace) -> int | None:
    from .deploy_check import run_cli

    return run_cli(strict=args.strict, live=args.live)


def _cmd_cashflow_delivery(args: argparse.Namespace) -> int:
    from .cashflow_delivery import (
        CashflowDeliveryError,
        deliver,
        load_executable,
        load_selection,
        write_failure_receipt,
    )

    try:
        selection_path = Path(args.selection).expanduser().resolve()
        if args.artifact_kind == "executable":
            artifact = load_executable(
                selection_path,
                expected_source_date=args.source_date,
                expected_signal_date=args.signal_date,
            )
        else:
            artifact = load_selection(
                selection_path,
                expected_source_date=args.source_date,
                expected_signal_date=args.signal_date,
            )
        receipt = deliver(
            artifact=artifact,
            selection_path=selection_path,
            publication_receipt_path=Path(args.publication_receipt).expanduser().resolve(),
            receipt_path=Path(args.receipt).expanduser().resolve(),
            chat_ids=args.chat_id,
            lark_cli=args.lark_cli,
            dry_run=args.dry_run,
            artifact_kind=args.artifact_kind,
        )
    except CashflowDeliveryError as exc:
        write_failure_receipt(
            Path(args.receipt).expanduser().resolve(),
            source_date=str(args.source_date),
            signal_date=str(args.signal_date),
            error=str(exc),
        )
        print(f"[FAIL] cashflow Feishu delivery: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["success"] else 1


def _cmd_cashflow_status_notify(args: argparse.Namespace) -> int:
    from .cashflow_status_notify import CashflowStatusError, deliver_status

    try:
        status = json.loads(Path(args.status_json).expanduser().read_text(encoding="utf-8"))
        receipt = deliver_status(
            status=status,
            receipt_path=Path(args.receipt).expanduser().resolve(),
            chat_ids=args.chat_id,
            lark_cli=args.lark_cli,
            dry_run=not args.send,
            send_confirmation=args.send_confirmation,
        )
    except (OSError, json.JSONDecodeError, CashflowStatusError) as exc:
        print(f"[FAIL] cashflow status notification: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["success"] else 1


def _cmd_cashflow_portfolio_render(args: argparse.Namespace) -> int:
    from .cashflow_portfolio_render import (
        enrich_cashflow_portfolio,
        render_cashflow_portfolio_markdown,
        render_cashflow_portfolio_png,
    )

    try:
        selection = json.loads(Path(args.selection).expanduser().read_text(encoding="utf-8"))
        if args.instruments:
            selection = enrich_cashflow_portfolio(selection, args.instruments)
        chart = render_cashflow_portfolio_png(selection, args.chart_out)
        print(
            json.dumps(
                {"chart": str(chart), "markdown": render_cashflow_portfolio_markdown(selection)},
                ensure_ascii=False,
                indent=2,
            )
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[FAIL] cashflow portfolio render: {exc}", file=sys.stderr)
        return 1
    return 0


def _load_weekly_basket_inputs(args: argparse.Namespace):
    from .weekly_client_basket import (
        BasketConfig,
        load_cashflow_selection,
        load_dailywatch_family,
        load_microcap_selection,
        load_previous_basket,
    )

    source_path = Path(args.d11_h5 or args.dailywatch).expanduser().resolve()
    source_positions = {
        "dailywatch_family": load_dailywatch_family(source_path, as_of_date=args.as_of_date),
        "cashflow": load_cashflow_selection(
            Path(args.cashflow).expanduser().resolve(),
            Path(args.cashflow_receipt).expanduser().resolve(),
            as_of_date=args.as_of_date,
        ),
    }
    source_positions["microcap"] = (
        load_microcap_selection(
            Path(args.microcap).expanduser().resolve(),
            as_of_date=args.as_of_date,
        )
        if args.microcap_quota
        else []
    )
    config = BasketConfig(
        quotas={
            "dailywatch_family": 10 - 3 - args.microcap_quota,
            "cashflow": 3,
            "microcap": args.microcap_quota,
        }
    )
    previous = (
        load_previous_basket(Path(args.previous).expanduser().resolve()) if args.previous else None
    )
    return source_positions, config, previous


def _update_weekly_basket_receipt(receipt_path: Path, delivery_path: Path, status: str) -> None:
    from .weekly_client_basket import _atomic_write

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["send_status"] = status
    payload["delivery_receipt"] = str(delivery_path)
    _atomic_write(
        receipt_path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def _cmd_weekly_basket(args: argparse.Namespace) -> int:
    from .weekly_client_basket import (
        WeeklyBasketError,
        compose_weekly_basket,
        write_basket_artifacts,
    )
    from .weekly_client_basket_delivery import send_personal_basket_report
    from .weekly_client_basket_render import render_basket_markdown, write_rendered_outputs

    if args.send and args.dry_run:
        print("[FAIL] --send and --dry-run cannot be used together", file=sys.stderr)
        return 1
    if args.microcap_quota and not args.microcap:
        print("[FAIL] --microcap is required when --microcap-quota is non-zero", file=sys.stderr)
        return 1
    try:
        source_positions, config, previous = _load_weekly_basket_inputs(args)
        artifact = compose_weekly_basket(
            source_positions,
            as_of_date=args.as_of_date,
            previous_basket=previous,
            config=config,
        )
        output_root = Path(args.output_root).expanduser().resolve()
        paths = write_basket_artifacts(artifact, output_root)
        rendered = write_rendered_outputs(artifact, output_root / args.as_of_date)
        markdown = render_basket_markdown(artifact)
        delivery = None
        if args.send:
            delivery = send_personal_basket_report(
                markdown,
                report_date=args.as_of_date,
                chat_id=args.personal_chat_id or "",
                lark_cli=args.lark_cli,
                receipt_path=output_root / args.as_of_date / "delivery_receipt.json",
            )
            _update_weekly_basket_receipt(
                paths["receipt"],
                output_root / args.as_of_date / "delivery_receipt.json",
                delivery.status,
            )
            if delivery.status != "sent":
                print(
                    json.dumps(
                        {
                            "paths": {key: str(value) for key, value in paths.items()},
                            "delivery": delivery.__dict__,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 1
        print(
            json.dumps(
                {
                    "report_date": artifact.report_date,
                    "positions": len(artifact.positions),
                    "paths": {
                        **{key: str(value) for key, value in paths.items()},
                        **{key: str(value) for key, value in rendered.items()},
                    },
                    "send_status": delivery.status if delivery else "not_requested",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, WeeklyBasketError, ValueError) as exc:
        print(f"[FAIL] weekly basket: {exc}", file=sys.stderr)
        return 1


def _cmd_evening_review(args: argparse.Namespace) -> int | None:
    from .review import build_json as review_json
    from .review import build_report

    trade_date = args.date
    if not trade_date:
        from . import data as D

        trade_date = D._latest_date("daily")
        if not trade_date:
            print("[FAIL] cannot determine latest trading date", file=sys.stderr)
            return 1

    output = review_json(trade_date) if args.json else build_report(trade_date)
    print(output)
    return _maybe_send_feishu(output, args)


def _dispatch(args: argparse.Namespace) -> int | None:
    """Route parsed ``args`` to the appropriate subcommand.

    Returns the process exit code (``None`` means exit 0). Delayed imports are
    intentional: they keep heavy optional dependencies out of the startup path.
    """
    if args.command == "morning":
        return _cmd_morning(args)

    if args.command == "morning-report":
        return _cmd_morning_report(args)

    if args.command == "daily-watch20":
        return _cmd_daily_watch20(args)

    if args.command == "doctor":
        return _cmd_doctor(args)

    if args.command == "cashflow-delivery":
        return _cmd_cashflow_delivery(args)

    if args.command == "cashflow-status-notify":
        return _cmd_cashflow_status_notify(args)

    if args.command == "cashflow-portfolio-render":
        return _cmd_cashflow_portfolio_render(args)

    if args.command == "weekly-basket":
        return _cmd_weekly_basket(args)

    return _cmd_evening_review(args)


def main() -> None:
    _configure_console_encoding()

    args = _build_parser().parse_args()
    code = _dispatch(args)
    if code is not None:
        sys.exit(code)
