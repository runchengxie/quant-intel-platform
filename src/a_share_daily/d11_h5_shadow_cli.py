"""Command-line orchestration for the D11-H5 research-only delivery."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ops_common.env import resolve_data_platform_root

from . import d11_h5_shadow_delivery as delivery

REQUIRED_GROUP_AUDIENCES = delivery.REQUIRED_GROUP_AUDIENCES


def _default_data_root() -> Path:
    return resolve_data_platform_root(required=True)


def _default_market_output_root() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return Path(
        os.environ.get(
            "D11_H5_DELIVERY_OUTPUT_ROOT",
            os.path.join(
                os.environ.get("A_SHARE_OUTPUT_DIR", str(project_root / "out/a_share_daily")),
                "d11_h5_shadow",
            ),
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deliver the research-only D11-H5 shadow")
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--strategy-root", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--strategy-output-root", type=Path)
    parser.add_argument("--bootstrap-root", type=Path)
    parser.add_argument("--output-root", type=Path, default=_default_market_output_root())
    parser.add_argument("--chat-id", action="append", default=[])
    parser.add_argument("--audience", default="personal")
    parser.add_argument("--delivery-audience", choices=("all", "client", "internal"), default="all")
    parser.add_argument("--lark-cli")
    parser.add_argument("--strategy-doc-url")
    parser.add_argument("--no-send", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_root = args.output_root.expanduser().resolve() / args.signal_date
    receipt_path = run_root / "delivery_receipt.json"
    targets = delivery._filtered_targets(
        explicit_chat_ids=args.chat_id,
        explicit_audience=args.audience,
        delivery_audience=args.delivery_audience,
    )
    required_audiences = tuple(targets)
    if args.check_only:
        delivery.validate_delivery_receipt(
            receipt_path,
            expected_source_date=args.source_date,
            expected_signal_date=args.signal_date,
            required_audiences=(required_audiences or REQUIRED_GROUP_AUDIENCES),
        )
        print(f"D11-H5 delivery healthy: {receipt_path}")
        return 0
    strategy_root_raw = args.strategy_root or os.environ.get("STRATEGY_PIPELINE_ROOT")
    if not strategy_root_raw:
        raise delivery.D11H5DeliveryError("STRATEGY_PIPELINE_ROOT / --strategy-root is required")
    strategy_root = Path(strategy_root_raw).expanduser().resolve()
    data_root = (args.data_root or _default_data_root()).expanduser().resolve()
    strategy_output_root = (
        args.strategy_output_root.expanduser().resolve()
        if args.strategy_output_root
        else data_root / "strategy_outputs/d11_h5_shadow"
    )
    selection_path = delivery._run_producer(
        strategy_root=strategy_root,
        data_root=data_root,
        strategy_output_root=strategy_output_root,
        bootstrap_root=args.bootstrap_root.expanduser().resolve()
        if args.bootstrap_root
        else (
            Path(os.environ["D11_H5_SHADOW_BOOTSTRAP_ROOT"]).expanduser().resolve()
            if os.environ.get("D11_H5_SHADOW_BOOTSTRAP_ROOT")
            else None
        ),
        source_date=args.source_date,
        signal_date=args.signal_date,
    )
    artifact = delivery.load_selection(
        selection_path,
        expected_source_date=args.source_date,
        expected_signal_date=args.signal_date,
    )
    markdown_path, image_path = delivery.render_selection(
        artifact,
        run_root / "render",
        strategy_doc_url=args.strategy_doc_url,
    )
    receipt = delivery.deliver(
        artifact=artifact,
        selection_path=selection_path,
        markdown_path=markdown_path,
        image_path=image_path,
        receipt_path=receipt_path,
        targets=targets,
        lark_cli=args.lark_cli,
        no_send=args.no_send,
    )
    print(
        json.dumps(
            {
                "status": "passed" if receipt.get("success") or args.no_send else "failed",
                "selection_path": str(selection_path),
                "markdown_path": str(markdown_path),
                "image_path": str(image_path),
                "receipt_path": str(receipt_path),
                "sent": bool(receipt.get("success")),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except delivery.D11H5DeliveryError as exc:
        print(f"[d11-h5-shadow] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
