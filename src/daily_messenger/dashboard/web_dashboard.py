"""Render the static market intelligence dashboard."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from daily_messenger.dashboard.payload import (
    DEFAULT_STATE_PANEL_NAME,
    OUT_DIR,
    SNAPSHOT_DIR,
    STATE_PANEL_ENV,
    _json_default,
    build_payload,
)

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "web_dashboard.html"
PAYLOAD_NAME = "web_dashboard_payload.json"


@dataclass(frozen=True)
class DashboardBuildResult:
    html_path: Path
    payload_path: Path | None


def _render_html(payload: Mapping[str, object]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_PATH.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(TEMPLATE_PATH.name)
    return template.render(payload=payload)


def build_dashboard(
    *,
    output_path: Path | None = None,
    out_dir: Path = OUT_DIR,
    snapshot_dir: Path = SNAPSHOT_DIR,
    state_panel_path: Path | None = None,
    write_payload_json: bool = True,
) -> DashboardBuildResult:
    destination = output_path or (out_dir / "web_dashboard.html")
    payload = build_payload(
        out_dir=out_dir,
        snapshot_dir=snapshot_dir,
        state_panel_path=state_panel_path,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_render_html(payload), encoding="utf-8")
    payload_path: Path | None = None
    if write_payload_json:
        payload_path = destination.with_name(PAYLOAD_NAME)
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    return DashboardBuildResult(html_path=destination, payload_path=payload_path)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build static market intelligence dashboard")
    parser.add_argument(
        "--out",
        default=str(OUT_DIR / "web_dashboard.html"),
        help="Output HTML path (default: out/web_dashboard.html)",
    )
    parser.add_argument(
        "--state-panel",
        default=None,
        help=(
            "Optional CSV with market-state proxy columns. "
            f"Defaults to ${STATE_PANEL_ENV} or out/{DEFAULT_STATE_PANEL_NAME} when present."
        ),
    )
    parser.add_argument(
        "--snapshot-dir",
        default=str(SNAPSHOT_DIR),
        help="Directory containing latest cross-market and TuShare snapshots.",
    )
    parser.add_argument(
        "--no-payload-json",
        action="store_true",
        help="Do not write web_dashboard_payload.json next to the HTML file.",
    )
    args = parser.parse_args(argv)
    state_panel = Path(args.state_panel) if args.state_panel else None
    result = build_dashboard(
        output_path=Path(args.out),
        out_dir=OUT_DIR,
        snapshot_dir=Path(args.snapshot_dir),
        state_panel_path=state_panel,
        write_payload_json=not args.no_payload_json,
    )
    print(f"Dashboard written to {result.html_path}")
    if result.payload_path:
        print(f"Payload written to {result.payload_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
