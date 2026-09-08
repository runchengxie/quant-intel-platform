"""Feishu delivery for the StyleReplica bridge.

Owns the internal-only delivery guard, the lark-cli subprocess calls, and the
daily push orchestration. Imports rendering helpers from ``.render`` so the
pure formatting code stays free of I/O.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import render as _render

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = Path(".market-intel-external-data-not-configured")
INTERNAL_FEISHU_USER_ENV = "STYLE_REPLICA_INTERNAL_FEISHU_USER_ID"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _lark_cli() -> str:
    return _env("LARK_CLI") or str(Path.home() / ".local" / "bin" / "lark-cli")


def _resolve_internal_delivery_user(
    user_id: str | None,
    *,
    internal_delivery: bool,
) -> str | None:
    """Resolve the allowlisted internal recipient or fail closed."""
    if not internal_delivery:
        print(
            "[style_replica] Refusing Feishu delivery: this legacy report is internal-only",
            file=sys.stderr,
        )
        return None
    configured = _env(INTERNAL_FEISHU_USER_ENV)
    if not configured:
        print(
            f"[style_replica] Refusing Feishu delivery: {INTERNAL_FEISHU_USER_ENV} is unset",
            file=sys.stderr,
        )
        return None
    requested = (user_id or configured).strip()
    if requested != configured:
        print(
            "[style_replica] Refusing Feishu delivery: recipient is not the internal allowlist",
            file=sys.stderr,
        )
        return None
    return configured


def send_to_user(
    markdown_text: str,
    *,
    user_id: str | None = None,
    lark_cli: str | None = None,
    dry_run: bool = False,
    internal_delivery: bool = False,
) -> bool:
    """Send an internal-only markdown message via lark-cli DM."""
    cli = lark_cli or _lark_cli()

    if dry_run:
        uid = (user_id or _env(INTERNAL_FEISHU_USER_ENV) or "internal-preview").strip()
        print(f"[style_replica] INTERNAL-ONLY DRY RUN — would send to {uid[:20]}...:")
        print(markdown_text[:1200])
        return True

    uid = _resolve_internal_delivery_user(
        user_id,
        internal_delivery=internal_delivery,
    )
    if uid is None:
        return False

    cmd = [
        cli,
        "im",
        "+messages-send",
        "--user-id",
        uid,
        "--markdown",
        markdown_text,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"[style_replica] lark-cli failed: {result.stderr[:300]}", file=sys.stderr)
            return False
        print(f"[style_replica] Sent DM to {uid[:20]}... OK")
        return True
    except Exception as exc:
        print(f"[style_replica] lark-cli error: {exc}", file=sys.stderr)
        return False


def _send_lark_image(
    image_path: str | Path,
    *,
    user_id: str | None = None,
    lark_cli: str | None = None,
    internal_delivery: bool = False,
) -> bool:
    """Send an internal-only image to a Feishu user via lark-cli."""
    cli = lark_cli or _lark_cli()
    uid = _resolve_internal_delivery_user(
        user_id,
        internal_delivery=internal_delivery,
    )
    if uid is None:
        return False

    img = Path(image_path).resolve()
    try:
        rel = str(img.relative_to(Path.cwd()))
    except ValueError:
        print(f"[style_replica] image not under CWD: {img}", file=sys.stderr)
        return False
    cmd = [cli, "im", "+messages-send", "--user-id", uid, "--image", rel]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def push_daily_holdings(
    positions_path: str | Path,
    *,
    signal_date: str | None = None,
    user_id: str | None = None,
    dry_run: bool = False,
    with_tearsheet: bool = True,
    internal_delivery: bool = False,
) -> bool:
    """Run the explicitly internal-only daily push pipeline.

    Args:
        positions_path: Path to positions CSV from StyleReplica pipeline.
        signal_date: Date string YYYYMMDD. Default: today.
        user_id: Feishu open_id to DM. Default: from env.
        dry_run: Print instead of sending.
        with_tearsheet: Generate and send charts + HTML report.
        internal_delivery: Explicit acknowledgement for the allowlisted internal recipient.

    Returns:
        True if push succeeded.
    """
    resolved_user_id = user_id
    if not dry_run:
        resolved_user_id = _resolve_internal_delivery_user(
            user_id,
            internal_delivery=internal_delivery,
        )
        if resolved_user_id is None:
            return False

    positions = _render.load_positions(positions_path)
    if positions.empty:
        print("[style_replica] Empty positions file", file=sys.stderr)
        return False

    # Enrich with factor-profile hot tags
    positions = _render.enrich_positions_with_tags(positions)

    date = signal_date or datetime.now().strftime("%Y%m%d")

    image_delivery_ok = True

    # Generate tearsheet charts + HTML report
    if with_tearsheet and not dry_run:
        from .tearsheet import generate_tearsheet

        out_dir = (
            Path(positions_path).parent
            if isinstance(positions_path, (str, Path))
            else Path("out/style_replica") / date
        )
        artifacts = generate_tearsheet(positions, out_dir, signal_date=date)
        print(f"[style_replica] Tearsheet HTML: {artifacts.get('html_report', 'N/A')}")

        # Send chart images to Feishu
        for key in ("industry_chart", "theme_chart"):
            if key in artifacts:
                ok = _send_lark_image(
                    artifacts[key],
                    user_id=resolved_user_id,
                    internal_delivery=internal_delivery,
                )
                image_delivery_ok = image_delivery_ok and ok
                label = "行业Top10" if key == "industry_chart" else "主题分布"
                print(f"[style_replica] Sent {label}: {'OK' if ok else 'FAILED'}")

    message = _render.format_holdings_summary(positions, date)
    message_delivery_ok = send_to_user(
        message,
        user_id=resolved_user_id,
        dry_run=dry_run,
        internal_delivery=internal_delivery,
    )
    return image_delivery_ok and message_delivery_ok
