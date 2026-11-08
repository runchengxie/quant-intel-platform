"""Weekly basket CLI orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path


def _load_weekly_basket_inputs(args: argparse.Namespace):
    from .weekly_client_basket import (
        BasketConfig,
        enrich_source_names,
        load_cashflow_selection,
        load_microcap_selection,
    )

    source_positions = {
        "dailywatch_family": [],
        "cashflow": load_cashflow_selection(
            Path(args.cashflow).expanduser().resolve(),
            Path(args.cashflow_receipt).expanduser().resolve(),
            as_of_date=args.as_of_date,
        ),
    }
    source_positions["microcap"] = load_microcap_selection(
        Path(args.microcap).expanduser().resolve(),
        receipt_path=Path(args.microcap_receipt).expanduser().resolve(),
        as_of_date=args.as_of_date,
        allow_legacy=args.dry_run,
    )
    if args.instruments:
        import pandas as pd

        frame = pd.read_parquet(Path(args.instruments).expanduser().resolve())
        symbol_column = "symbol" if "symbol" in frame.columns else "ts_code"
        if symbol_column not in frame.columns or "name" not in frame.columns:
            raise ValueError("instrument snapshot must contain symbol/ts_code and name columns")
        names = dict(
            zip(
                frame[symbol_column].fillna("").astype(str).str.strip().str.upper(),
                frame["name"].fillna("").astype(str).str.strip(),
                strict=False,
            )
        )
        source_positions = enrich_source_names(source_positions, names)
    config = BasketConfig(
        quotas={
            "dailywatch_family": 0,
            "cashflow": 6,
            "microcap": 4,
        }
    )
    return source_positions, config


def _update_weekly_basket_receipt(
    receipt_path: Path, delivery_path: Path | None, status: str
) -> None:
    from .weekly_client_basket import _atomic_write

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["send_status"] = status
    if delivery_path is not None:
        payload["delivery_receipt"] = str(delivery_path)
    _atomic_write(
        receipt_path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def _prepare_weekly_basket(args: argparse.Namespace):
    from .weekly_basket_state import (
        acquire_weekly_lock,
        load_previous_successful_basket,
        load_weekly_lock,
    )
    from .weekly_client_basket import basket_artifact_from_payload, compose_weekly_basket
    from .weekly_client_basket_delivery import personal_chat_id

    target = personal_chat_id(args.personal_chat_id)
    target_hash = hashlib.sha256(target.encode()).hexdigest()[:16]
    report_week = datetime.strptime(args.as_of_date, "%Y%m%d").strftime("%G-W%V")
    state_root = Path(args.state_root).expanduser().resolve()
    source_state_root = Path(getattr(args, "source_state_root", state_root)).expanduser().resolve()
    previous_payload = load_previous_successful_basket(
        source_state_root, report_week=report_week, target_hash=target_hash
    )
    previous = basket_artifact_from_payload(previous_payload) if previous_payload else None
    source_positions, config = _load_weekly_basket_inputs(args)
    artifact = compose_weekly_basket(
        source_positions,
        as_of_date=args.as_of_date,
        previous_basket=previous,
        config=config,
    )
    from .weekly_basket_preflight import run_weekly_basket_preflight

    preflight = run_weekly_basket_preflight(
        artifact.positions,
        report_date=args.as_of_date,
        instruments_path=Path(args.instruments).expanduser().resolve(),
        market_path=Path(args.market_snapshot).expanduser().resolve(),
        calendar_path=Path(args.calendar).expanduser().resolve(),
        enforce_stable_paths=not args.dry_run,
    )
    basket_payload = {
        "schema_version": artifact.schema_version,
        "report_date": artifact.report_date,
        "config": {
            "quotas": dict(artifact.config.quotas),
            "allow_microcap_shadow": artifact.config.allow_microcap_shadow,
        },
        "positions": [asdict(row) for row in artifact.positions],
        "trade_delta": asdict(artifact.trade_delta),
        "source_inputs": list(artifact.source_inputs),
    }
    input_hashes = {
        **preflight.input_hashes,
        "cashflow_receipt": hashlib.sha256(
            Path(args.cashflow_receipt).expanduser().resolve().read_bytes()
        ).hexdigest(),
        "microcap_receipt": hashlib.sha256(
            Path(args.microcap_receipt).expanduser().resolve().read_bytes()
        ).hexdigest(),
        **{
            f"{row['sleeve']}:{index}": row["artifact_sha256"]
            for index, row in enumerate(artifact.source_inputs)
        },
    }
    if args.performance:
        input_hashes["performance"] = hashlib.sha256(
            Path(args.performance).expanduser().resolve().read_bytes()
        ).hexdigest()
    if args.dry_run and not args.override_weekly_lock:
        frozen = load_weekly_lock(
            source_state_root, report_week=report_week, target_hash=target_hash
        )
        if frozen is not None:
            return frozen
    return acquire_weekly_lock(
        state_root,
        report_week=preflight.report_week,
        target_hash=target_hash,
        basket=basket_payload,
        input_hashes=input_hashes,
        override=args.override_weekly_lock,
        override_reason=args.override_reason,
    )


def _write_weekly_basket_outputs(args, lock, performance):
    from .weekly_client_basket import basket_artifact_from_payload, write_basket_artifacts
    from .weekly_client_basket_render import write_rendered_outputs

    artifact = basket_artifact_from_payload(lock.basket)
    output_root = Path(args.output_root).expanduser().resolve()
    paths = write_basket_artifacts(artifact, output_root)
    rendered = write_rendered_outputs(
        artifact,
        output_root / args.as_of_date,
        theme=args.theme,
        performance=performance,
    )
    markdown = rendered["markdown"].read_bytes().decode("utf-8")
    if args.dry_run:
        _update_weekly_basket_receipt(paths["receipt"], None, "dry_run")
    return artifact, paths, rendered, markdown


def _deliver_weekly_basket(args, paths, rendered, markdown):
    from .weekly_client_basket_delivery import send_basket_report

    deliveries = []
    if not args.send:
        return deliveries, True

    delivery_dir = Path(args.output_root).expanduser().resolve() / args.as_of_date / "delivery"
    targets = [("personal", args.personal_chat_id)]
    if not args.personal_only:
        targets.append(("group", args.group_chat_id))
    for target_kind, target_id in targets:
        deliveries.append(
            send_basket_report(
                markdown,
                report_date=args.as_of_date,
                target_id=target_id,
                target_kind=target_kind,
                lark_cli=args.lark_cli,
                receipt_path=delivery_dir / f"{target_kind}.json",
                image_path=rendered.get("png"),
                render_manifest_path=rendered.get("manifest"),
                sender_scope=args.sender_scope,
                delivery_state_root=Path(args.state_root).expanduser().resolve() / "delivery",
                legacy_receipt_root=Path(args.output_root).expanduser().resolve(),
            )
        )
    overall_status = (
        "sent"
        if deliveries
        and all(
            row.status == "sent"
            and row.image_status == ("sent" if rendered.get("png") else "not_requested")
            for row in deliveries
        )
        else "failed"
    )
    _update_weekly_basket_receipt(
        paths["receipt"],
        Path(args.state_root).expanduser().resolve() / "delivery",
        overall_status,
    )
    if overall_status != "sent":
        print(
            json.dumps(
                {
                    "paths": {key: str(value) for key, value in paths.items()},
                    "deliveries": [row.public_projection() for row in deliveries],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return deliveries, overall_status == "sent"


def _require_sender_scope(args: argparse.Namespace) -> None:
    if args.send and not (args.sender_scope or "").strip():
        raise ValueError("--sender-scope is required for --send")


def _preview_args(args: argparse.Namespace) -> argparse.Namespace:
    """Keep preview artifacts and freeze records outside canonical namespaces."""
    preview = argparse.Namespace(**vars(args))
    preview.source_state_root = args.state_root
    task_id = uuid.uuid4().hex
    preview.output_root = str(Path(args.output_root).expanduser().resolve() / "previews" / task_id)
    preview.state_root = str(Path(args.state_root).expanduser().resolve() / "previews" / task_id)
    return preview


def _cmd_weekly_basket(args: argparse.Namespace) -> int:
    from .weekly_client_basket import WeeklyBasketError

    if args.send and args.dry_run:
        print("[FAIL] --send and --dry-run cannot be used together", file=sys.stderr)
        return 1
    if args.send and not args.performance:
        print("[FAIL] weekly basket: --performance is required for --send", file=sys.stderr)
        return 1
    try:
        performance = None
        if args.performance:
            from .reporting.performance import load_performance

            performance = load_performance(
                Path(args.performance).expanduser().resolve(),
                report_date=args.as_of_date,
                allow_legacy=args.dry_run,
            ).to_payload()
        if args.send and not args.personal_only and not args.group_chat_id:
            print("[FAIL] weekly basket: --group-chat-id is required for --send", file=sys.stderr)
            return 1

        _require_sender_scope(args)
        if args.dry_run:
            args = _preview_args(args)
        lock = _prepare_weekly_basket(args)
        artifact, paths, rendered, markdown = _write_weekly_basket_outputs(args, lock, performance)
        deliveries, sent = _deliver_weekly_basket(args, paths, rendered, markdown)
        if not sent:
            return 1
        print(
            json.dumps(
                {
                    "report_date": artifact.report_date,
                    "positions": len(artifact.positions),
                    "deliveries": [row.public_projection() for row in deliveries],
                    "paths": {
                        **{key: str(value) for key, value in paths.items()},
                        **{key: str(value) for key, value in rendered.items()},
                    },
                    "send_status": (
                        "sent" if deliveries else "dry_run" if args.dry_run else "not_requested"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, WeeklyBasketError, ValueError) as exc:
        print(f"[FAIL] weekly basket: {exc}", file=sys.stderr)
        return 1
