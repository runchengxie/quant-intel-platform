"""Deterministic report delivery for A-share morning/evening reports.

This module has been physically split into focused submodules under
``a_share_daily.delivery`` (``io_util``, ``targets``, ``senders``, ``state``).
Every moved symbol is re-imported here so external callers and tests that
do ``from a_share_daily.delivery import report_delivery`` or
``monkeypatch.setattr(report_delivery, "<symbol>", ...)`` keep working
unchanged. Orchestration functions (``deliver_morning``, ``deliver_evening``,
``run`` and the chart-path helpers) remain defined in this file.
"""

from __future__ import annotations

__all__ = [
    "CATEGORY_LABELS",
    "NEWS_MARKET_LABELS",
    "NEWS_MARKET_ORDER",
    "_MARKET_TEMPERATURE_DIMENSIONS",
    "_chart_paths",
    "_date_dash",
    "_deliver_markdown_files_and_images",
    "_dict",
    "_fmt_close",
    "_fmt_pct",
    "_fmt_score",
    "_fmt_yuan",
    "_list",
    "_load_json",
    "_manifest_chart_paths",
    "_news_error_lines",
    "_news_items",
    "_quote_line",
    "_read_text",
    "_render_evening_asia",
    "_render_evening_macro",
    "_render_evening_market_temperature",
    "_render_evening_news",
    "_render_evening_next_watch",
    "_render_evening_transmission",
    "_render_evening_us_preview",
    "_send_morning_charts",
    "_write_text",
    "build_evening_summary",
    "deliver_evening",
    "deliver_morning",
    "run",
    "subprocess",
]
import argparse
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from a_share_daily.delivery import io_util, senders, state, targets
from a_share_daily.delivery._format import (
    _date_dash,
    _dict,
    _fmt_close,
    _fmt_pct,
    _fmt_yuan,
    _list,
    _load_json,
    _read_text,
    _write_text,
)
from a_share_daily.delivery._render import (
    _MARKET_TEMPERATURE_DIMENSIONS,
    CATEGORY_LABELS,
    NEWS_MARKET_LABELS,
    NEWS_MARKET_ORDER,
    _fmt_score,
    _news_error_lines,
    _news_items,
    _quote_line,
    _render_evening_asia,
    _render_evening_macro,
    _render_evening_market_temperature,
    _render_evening_news,
    _render_evening_next_watch,
    _render_evening_transmission,
    _render_evening_us_preview,
    build_evening_summary,
)


def _send_morning_charts(
    out_dir: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    manifest_path: Path | None = None,
    chat_id: str | None = None,
    target: str | None = None,
    hermes_cli: str | None = None,
    lark_cli: str | None = None,
) -> None:
    """Send morning charts via Hermes, with lark-cli fallback."""
    chart_paths = _chart_paths(
        out_dir,
        manifest=manifest,
        manifest_path=manifest_path,
        chart_specs=io_util.MORNING_CHARTS,
        chart_keys=io_util.MORNING_CHART_KEYS,
    )
    labels = {filename: label for label, filename in io_util.MORNING_CHARTS}
    for image in chart_paths:
        label = labels.get(image.name, image.stem)
        hermes_ok = senders._send_hermes_image(
            image, chat_id=chat_id, target=target, hermes_cli=hermes_cli
        )
        if hermes_ok:
            print(f"[report_delivery] morning chart sent: {label}", file=sys.stderr)
        else:
            lark_ok = senders._send_lark_image(image, chat_id=chat_id, lark_cli=lark_cli)
            if lark_ok:
                print(
                    f"[report_delivery] morning chart sent via lark-cli: {label}", file=sys.stderr
                )
            else:
                print(f"[report_delivery] morning chart failed: {label}", file=sys.stderr)


def _deliver_via_lark(
    *,
    context: senders._DeliveryContext,
    kind: str,
    trade_date: str,
    text_files: Sequence[tuple[Path, str, str]],
    image_paths: Sequence[Path],
    routes: dict[str, Any],
    mode: str,
    message_ids: dict[str, list[str]] | None = None,
) -> tuple[bool, bool]:
    lark_preflight = senders._ensure_lark_ready(
        lark_cli=context.lark_cli, has_targets=bool(context.lark_targets)
    )
    routes["lark_preflight"] = lark_preflight
    if not lark_preflight.get("ok"):
        return (False, False)
    lark_text_results = [
        senders._send_lark_markdown(
            _read_text(path),
            chat_id=context.chat_id,
            user_id=context.user_id,
            lark_cli=context.lark_cli,
            idempotency_scope=(kind, trade_date, path.name),
            message_ids=(
                message_ids.setdefault("lark_text", []) if message_ids is not None else None
            ),
        )
        for path, _subject, _title in text_files
    ]
    lark_text_ok = all(lark_text_results) if lark_text_results else True
    lark_image_results = [
        senders._send_lark_image(
            image,
            chat_id=context.chat_id,
            user_id=context.user_id,
            lark_cli=context.lark_cli,
            message_ids=(
                message_ids.setdefault("lark_images", []) if message_ids is not None else None
            ),
        )
        for image in image_paths
    ]
    lark_images_ok = all(lark_image_results) if lark_image_results else True
    routes["lark_text"] = lark_text_ok
    routes["lark_images"] = lark_images_ok
    if lark_text_ok and lark_images_ok:
        print(f"[report_delivery] {kind} lark-cli delivery completed", file=sys.stderr)
    elif mode == "lark":
        state._write_delivery_status(
            kind=kind,
            trade_date=trade_date,
            mode=mode,
            success=False,
            routes=routes,
            artifacts=[],
            lark_targets=context.lark_targets,
            hermes_targets=context.hermes_targets,
        )
        return (False, False)
    return (lark_text_ok, lark_images_ok)


def _deliver_via_hermes(
    *,
    context: senders._DeliveryContext,
    kind: str,
    trade_date: str,
    text_files: Sequence[tuple[Path, str, str]],
    image_paths: Sequence[Path],
    routes: dict[str, Any],
    mode: str,
    lark_text_ok: bool,
    lark_images_ok: bool,
) -> tuple[bool, bool]:
    if mode != "both" and lark_text_ok:
        hermes_text_ok = True
    else:
        hermes_text_results = [
            senders._send_hermes_file(
                path,
                subject=subject,
                chat_id=context.chat_id,
                target=context.hermes_target,
                hermes_cli=context.hermes_cli,
            )
            for path, subject, _title in text_files
        ]
        hermes_text_ok = all(hermes_text_results) if hermes_text_results else True
    if mode != "both" and lark_images_ok:
        hermes_images_ok = True
    else:
        hermes_image_results = [
            senders._send_hermes_image(
                image,
                chat_id=context.chat_id,
                target=context.hermes_target,
                hermes_cli=context.hermes_cli,
            )
            for image in image_paths
        ]
        hermes_images_ok = all(hermes_image_results) if hermes_image_results else True
    routes["hermes_text"] = hermes_text_ok
    routes["hermes_images"] = hermes_images_ok
    if hermes_text_ok and hermes_images_ok:
        print(f"[report_delivery] {kind} hermes delivery completed", file=sys.stderr)
    elif mode == "hermes":
        state._write_delivery_status(
            kind=kind,
            trade_date=trade_date,
            mode=mode,
            success=False,
            routes=routes,
            artifacts=[],
            lark_targets=context.lark_targets,
            hermes_targets=context.hermes_targets,
        )
        return (False, False)
    return (hermes_text_ok, hermes_images_ok)


def _deliver_via_webhook(
    *, text_files: Sequence[tuple[Path, str, str]], routes: dict[str, Any], webhook_enabled_env: str
) -> bool:
    webhook_results = [
        senders._send_webhook_text(path, title=title, enabled_env=webhook_enabled_env)
        for path, _subject, title in text_files
    ]
    webhook_ok = all(webhook_results) if webhook_results else True
    routes["webhook_text"] = webhook_ok
    return webhook_ok


def _deliver_markdown_files_and_images(
    *,
    kind: str,
    trade_date: str,
    context: senders._DeliveryContext,
    text_files: Sequence[tuple[Path, str, str]],
    image_paths: Sequence[Path],
    artifacts: Sequence[dict[str, Any]],
    webhook_enabled_env: str,
    allow_webhook: bool = True,
    signal_date: str | None = None,
) -> bool:
    mode = context.mode
    message_ids: dict[str, list[str]] = {}
    effective_signal_date = signal_date or trade_date
    idempotency_key = state.delivery_idempotency_key(
        kind=kind,
        trade_date=trade_date,
        signal_date=effective_signal_date,
        mode=mode,
        routes={},
        artifacts=artifacts,
        lark_targets=context.lark_targets,
        hermes_targets=context.hermes_targets,
    )
    if state.has_successful_delivery(
        state._delivery_state_dir() / f"{kind}_latest.json", idempotency_key
    ):
        print(f"[report_delivery] {kind} already delivered; skipping duplicate", file=sys.stderr)
        return True
    base = kind.split("_", 1)[0]
    should_lark = senders._route_enabled(base, "lark", mode)
    should_hermes = senders._route_enabled(base, "hermes", mode)
    should_webhook = allow_webhook and senders._route_enabled(base, "webhook", mode)
    routes = senders._empty_routes()
    if mode == "none":
        senders._write_disabled_delivery(
            kind=kind, trade_date=trade_date, context=context, artifacts=artifacts
        )
        return True
    lark_text_ok, lark_images_ok = (False, False)
    if should_lark:
        lark_text_ok, lark_images_ok = _deliver_via_lark(
            context=context,
            kind=kind,
            trade_date=trade_date,
            text_files=text_files,
            image_paths=image_paths,
            routes=routes,
            mode=mode,
            message_ids=message_ids,
        )
        if mode == "lark" and (not (lark_text_ok and lark_images_ok)):
            return False
    hermes_text_ok, hermes_images_ok = (False, False)
    if should_hermes and (mode == "both" or not (lark_text_ok and lark_images_ok)):
        hermes_text_ok, hermes_images_ok = _deliver_via_hermes(
            context=context,
            kind=kind,
            trade_date=trade_date,
            text_files=text_files,
            image_paths=image_paths,
            routes=routes,
            mode=mode,
            lark_text_ok=lark_text_ok,
            lark_images_ok=lark_images_ok,
        )
        if mode == "hermes" and (not (hermes_text_ok and hermes_images_ok)):
            return False
    text_delivered = hermes_text_ok or lark_text_ok
    images_delivered = hermes_images_ok or lark_images_ok or (not image_paths)
    webhook_ok = False
    if should_webhook and (mode in {"webhook", "both"} or not text_delivered):
        webhook_ok = _deliver_via_webhook(
            text_files=text_files, routes=routes, webhook_enabled_env=webhook_enabled_env
        )
        text_delivered = text_delivered or webhook_ok
    success = text_delivered and images_delivered or (mode == "webhook" and webhook_ok)
    state._write_delivery_status(
        kind=kind,
        trade_date=trade_date,
        signal_date=effective_signal_date,
        mode=mode,
        success=success,
        routes=routes,
        artifacts=artifacts,
        lark_targets=context.lark_targets,
        hermes_targets=context.hermes_targets,
        message_ids=message_ids,
    )
    return success


def _prepare_morning_context(
    args: argparse.Namespace,
) -> tuple[senders._DeliveryContext, str, str, list[Path], list[dict[str, Any]], str]:
    report_path = Path(args.report).expanduser()
    _read_text(report_path)
    explicit_target = any(
        getattr(args, name, None) for name in ("chat_id", "user_id", "hermes_target")
    )
    segmented_targets = targets._segmented_daily_targets_configured()
    internal_chat_id = targets._audience_chat_id("internal")
    context = (
        senders._delivery_context(args, chat_id_override=internal_chat_id)
        if segmented_targets and (not explicit_target) and internal_chat_id
        else senders._delivery_context(args)
    )
    mode = context.mode
    manifest_arg = getattr(args, "manifest", None)
    manifest_path = (
        Path(manifest_arg).expanduser()
        if manifest_arg
        else report_path.parent / "morning_manifest.json"
    )
    manifest_payload = _load_json(manifest_path)
    manifest_for_charts = manifest_payload if manifest_payload else None
    chart_paths = _chart_paths(
        report_path.parent,
        manifest=manifest_for_charts,
        manifest_path=manifest_path,
        expected_date=str(manifest_payload.get("date") or "") or None,
        chart_specs=io_util.MORNING_CHARTS,
        chart_keys=io_util.MORNING_CHART_KEYS,
    )
    trade_date = str(manifest_payload.get("date") or datetime.now().strftime("%Y%m%d"))
    signal_date = str(manifest_payload.get("signal_date") or trade_date)
    artifacts = [state._artifact_entry(report_path, role="morning_report")]
    artifacts.extend(state._artifact_entry(path, role="chart") for path in chart_paths)
    return (context, trade_date, signal_date, chart_paths, artifacts, mode)


def _deliver_morning_routes(
    *,
    args: argparse.Namespace,
    context: senders._DeliveryContext,
    trade_date: str,
    signal_date: str,
    text: str,
    chart_paths: list[Path],
    artifacts: list[dict[str, Any]],
    mode: str,
) -> int:
    idempotency_key = state.delivery_idempotency_key(
        kind="morning",
        trade_date=trade_date,
        signal_date=signal_date,
        mode=mode,
        routes={},
        artifacts=artifacts,
        lark_targets=context.lark_targets,
        hermes_targets=context.hermes_targets,
    )
    if state.has_successful_delivery(
        state._delivery_state_dir() / "morning_latest.json", idempotency_key
    ):
        print("[report_delivery] morning already delivered; skipping duplicate", file=sys.stderr)
        return 0
    should_hermes = senders._route_enabled("morning", "hermes", mode)
    should_lark = senders._route_enabled("morning", "lark", mode)
    should_webhook = senders._route_enabled("morning", "webhook", mode)
    routes = senders._empty_routes()
    message_ids: dict[str, list[str]] = {}
    if mode == "none":
        senders._write_disabled_delivery(
            kind="morning", trade_date=trade_date, context=context, artifacts=artifacts
        )
        return 0
    lark_ok = False
    if should_lark:
        lark_preflight = senders._ensure_lark_ready(
            lark_cli=context.lark_cli, has_targets=bool(context.lark_targets)
        )
        routes["lark_preflight"] = lark_preflight
        if lark_preflight.get("ok"):
            lark_text_ok = senders._send_lark_markdown(
                text,
                chat_id=context.chat_id,
                user_id=context.user_id,
                lark_cli=context.lark_cli,
                message_ids=message_ids.setdefault("lark_text", []),
                idempotency_scope=("morning", trade_date, "morning_report"),
            )
            lark_image_results = [
                senders._send_lark_image(
                    image,
                    chat_id=context.chat_id,
                    user_id=context.user_id,
                    lark_cli=context.lark_cli,
                    message_ids=message_ids.setdefault("lark_images", []),
                )
                for image in chart_paths
            ]
            lark_images_ok = all(lark_image_results) if lark_image_results else True
        else:
            lark_text_ok = False
            lark_images_ok = False
        routes["lark_text"] = lark_text_ok
        routes["lark_images"] = lark_images_ok
        lark_ok = lark_text_ok and lark_images_ok
        if lark_ok:
            print("[report_delivery] morning lark-cli delivery completed", file=sys.stderr)
        elif mode == "lark":
            state._write_delivery_status(
                kind="morning",
                trade_date=trade_date,
                signal_date=signal_date,
                mode=mode,
                success=False,
                routes=routes,
                artifacts=artifacts,
                lark_targets=context.lark_targets,
                hermes_targets=context.hermes_targets,
                message_ids=message_ids,
            )
            return 1
    hermes_ok = False
    if should_hermes and (mode == "both" or not lark_ok):
        hermes_ok = senders._send_hermes_file(
            Path(args.report).expanduser(),
            subject="亚洲市场盘前 / 美股市场盘后",
            chat_id=context.chat_id,
            target=context.hermes_target,
            hermes_cli=context.hermes_cli,
        )
        hermes_image_results = [
            senders._send_hermes_image(
                image,
                chat_id=context.chat_id,
                target=context.hermes_target,
                hermes_cli=context.hermes_cli,
            )
            for image in chart_paths
        ]
        hermes_images_ok = all(hermes_image_results) if hermes_image_results else True
        routes["hermes_text"] = hermes_ok
        routes["hermes_images"] = hermes_images_ok
        hermes_ok = hermes_ok and hermes_images_ok
        if hermes_ok:
            print("[report_delivery] morning hermes delivery completed", file=sys.stderr)
        elif mode == "hermes":
            state._write_delivery_status(
                kind="morning",
                trade_date=trade_date,
                signal_date=signal_date,
                mode=mode,
                success=False,
                routes=routes,
                artifacts=artifacts,
                lark_targets=context.lark_targets,
                hermes_targets=context.hermes_targets,
                message_ids=message_ids,
            )
            return 1
    webhook_ok = False
    if should_webhook and (mode in {"webhook", "both"} or (not hermes_ok and (not lark_ok))):
        webhook_ok = senders._send_webhook_text(
            Path(args.report).expanduser(),
            title="亚洲市场盘前 / 美股市场盘后",
            enabled_env="MORNING_SEND_WEBHOOK",
        )
        routes["webhook_text"] = webhook_ok
    webhook_text_only_ok = webhook_ok and (not chart_paths)
    success = lark_ok or hermes_ok or (mode == "webhook" and webhook_ok) or webhook_text_only_ok
    state._write_delivery_status(
        kind="morning",
        trade_date=trade_date,
        signal_date=signal_date,
        mode=mode,
        success=success,
        routes=routes,
        artifacts=artifacts,
        lark_targets=context.lark_targets,
        hermes_targets=context.hermes_targets,
        message_ids=message_ids,
    )
    return 0 if success else 1


def deliver_morning(args: argparse.Namespace) -> int:
    report_path = Path(args.report).expanduser()
    text = _read_text(report_path)
    context, trade_date, signal_date, chart_paths, artifacts, mode = _prepare_morning_context(args)
    _require_chart_bundle(
        chart_paths,
        expected=len(io_util.MORNING_CHARTS),
        kind="morning",
        required=os.environ.get("A_SHARE_REQUIRE_COMPLETE_CHARTS", "0") == "1",
    )
    if (
        targets._segmented_daily_targets_configured()
        and (not any(getattr(args, name, None) for name in ("chat_id", "user_id", "hermes_target")))
        and (not targets._audience_chat_id("internal"))
    ):
        senders._write_disabled_delivery(
            kind="morning", trade_date=trade_date, context=context, artifacts=artifacts
        )
        return 0
    return _deliver_morning_routes(
        args=args,
        context=context,
        trade_date=trade_date,
        signal_date=signal_date,
        text=text,
        chart_paths=chart_paths,
        artifacts=artifacts,
        mode=mode,
    )


def _manifest_chart_paths(
    out_dir: Path,
    manifest: Mapping[str, Any],
    *,
    chart_specs: Sequence[tuple[str, str]],
    chart_keys: Mapping[str, str],
    manifest_path: Path | None = None,
    expected_date: str | None = None,
) -> list[Path] | None:
    charts = _dict(manifest.get("charts"))
    raw_paths = _dict(charts.get("paths"))
    if not raw_paths:
        return None
    manifest_date = str(manifest.get("date") or "").replace("-", "")
    if expected_date and manifest_date and (manifest_date != expected_date):
        print(
            f"[report_delivery] manifest date {manifest_date} != requested {expected_date}; skipping charts",
            file=sys.stderr,
        )
        return []
    skipped = {str(item) for item in _list(charts.get("skipped"))}
    resolved: list[Path] = []
    for _label, filename in chart_specs:
        key = chart_keys.get(filename, "")
        if key in skipped:
            continue
        raw_path = raw_paths.get(key)
        if not isinstance(raw_path, str) or not raw_path.strip():
            print(f"[report_delivery] chart missing from manifest: {key}", file=sys.stderr)
            continue
        path = io_util._resolve_chart_path(raw_path, out_dir)
        if not path.exists():
            print(f"[report_delivery] manifest chart path missing: {path}", file=sys.stderr)
            continue
        if not io_util._chart_is_fresh(path, manifest_path):
            continue
        resolved.append(path)
    return resolved


def _chart_paths(
    out_dir: Path,
    explicit: Sequence[str] | None = None,
    manifest: Mapping[str, Any] | None = None,
    manifest_path: Path | None = None,
    expected_date: str | None = None,
    chart_specs: Sequence[tuple[str, str]] = io_util.EVENING_CHARTS,
    chart_keys: Mapping[str, str] = io_util.EVENING_CHART_KEYS,
) -> list[Path]:
    if explicit:
        return [io_util._resolve_chart_path(item, out_dir) for item in explicit]
    if manifest:
        manifest_paths = _manifest_chart_paths(
            out_dir,
            manifest,
            chart_specs=chart_specs,
            chart_keys=chart_keys,
            manifest_path=manifest_path,
            expected_date=expected_date,
        )
        if manifest_paths is not None:
            return manifest_paths
    if manifest_path is not None and (not manifest_path.exists()):
        print(
            f"[report_delivery] manifest missing, skipping charts: {manifest_path}", file=sys.stderr
        )
        return []
    paths = [out_dir / filename for _label, filename in chart_specs]
    if manifest_path is not None and manifest_path.exists():
        paths = [
            path for path in paths if path.exists() and io_util._chart_is_fresh(path, manifest_path)
        ]
    return paths


def _require_chart_bundle(
    chart_paths: Sequence[Path], *, expected: int, kind: str, required: bool
) -> None:
    if not required:
        return
    if len(chart_paths) != expected:
        detail = f"{kind} chart bundle has {len(chart_paths)} of {expected} charts"
        print(f"[report_delivery] ERROR: {detail}", file=sys.stderr)
        raise ValueError(detail)
    missing = [str(path) for path in chart_paths if not path.is_file()]
    if missing:
        detail = f"{kind} chart bundle contains missing files: {', '.join(missing)}"
        print(f"[report_delivery] ERROR: {detail}", file=sys.stderr)
        raise ValueError(detail)


def deliver_evening(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir).expanduser()
    summary_path = Path(args.summary_out).expanduser()
    review_path = Path(args.review).expanduser()
    manifest_path = Path(args.manifest).expanduser() if getattr(args, "manifest", None) else None
    manifest_payload = _load_json(manifest_path)
    signal_date = str(manifest_payload.get("signal_date") or args.date)
    chart_paths = _chart_paths(
        out_dir,
        getattr(args, "chart", None),
        manifest_payload,
        manifest_path=manifest_path,
        expected_date=args.date,
    )
    _require_chart_bundle(
        chart_paths,
        expected=len(io_util.EVENING_CHARTS),
        kind="evening",
        required=os.environ.get("A_SHARE_REQUIRE_COMPLETE_CHARTS", "0") == "1",
    )
    summary = build_evening_summary(
        args.date,
        review_payload=_load_json(args.review_json),
        news_payload=_load_json(args.news),
        manifest_payload=manifest_payload,
    )
    _write_text(summary_path, summary)
    artifacts = [
        state._artifact_entry(summary_path, role="evening_summary"),
        state._artifact_entry(review_path, role="evening_review"),
    ]
    artifacts.extend(state._artifact_entry(path, role="chart") for path in chart_paths)
    explicit_target = any(
        getattr(args, name, None) for name in ("chat_id", "user_id", "hermes_target")
    )
    if targets._segmented_daily_targets_configured() and (not explicit_target):
        client_chat_id = targets._audience_chat_id("client")
        internal_chat_id = targets._audience_chat_id("internal")
        skip_internal = os.environ.get("A_SHARE_SKIP_INTERNAL_DELIVERY", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        results: list[bool] = []
        lark_targets: list[str] = []
        hermes_targets: list[str] = []
        if client_chat_id:
            client_context = senders._delivery_context(args, chat_id_override=client_chat_id)
            lark_targets.extend(client_context.lark_targets)
            hermes_targets.extend(client_context.hermes_targets)
            results.append(
                _deliver_markdown_files_and_images(
                    kind="evening_client",
                    trade_date=args.date,
                    context=client_context,
                    text_files=[(review_path, "亚洲市场盘后信息", "亚洲市场盘后信息")],
                    image_paths=chart_paths,
                    artifacts=[state._artifact_entry(review_path, role="evening_review")]
                    + [state._artifact_entry(path, role="chart") for path in chart_paths],
                    webhook_enabled_env="EVENING_SEND_WEBHOOK",
                    allow_webhook=False,
                    signal_date=signal_date,
                )
            )
        if internal_chat_id and not skip_internal:
            internal_context = senders._delivery_context(args, chat_id_override=internal_chat_id)
            lark_targets.extend(internal_context.lark_targets)
            hermes_targets.extend(internal_context.hermes_targets)
            results.append(
                _deliver_markdown_files_and_images(
                    kind="evening_internal",
                    trade_date=args.date,
                    context=internal_context,
                    text_files=[
                        (
                            summary_path,
                            "美股市场盘前 / 亚洲市场盘后",
                            "美股市场盘前 / 亚洲市场盘后",
                        ),
                        (review_path, "完整盘后数据", "完整盘后数据"),
                    ],
                    image_paths=chart_paths,
                    artifacts=artifacts,
                    webhook_enabled_env="EVENING_SEND_WEBHOOK",
                    allow_webhook=False,
                    signal_date=signal_date,
                )
            )
        context = senders._delivery_context(args)
        success = all(results) if results else True
        state._write_delivery_status(
            kind="evening",
            trade_date=args.date,
            signal_date=signal_date,
            mode=context.mode,
            success=success,
            routes={
                "segmented": True,
                "client_enabled": bool(client_chat_id),
                "internal_enabled": bool(internal_chat_id and not skip_internal),
                "internal_skipped": bool(internal_chat_id and skip_internal),
                "webhook_disabled_for_segmented_delivery": True,
            },
            artifacts=artifacts,
            lark_targets=lark_targets,
            hermes_targets=hermes_targets,
        )
        return 0 if success else 1
    context = senders._delivery_context(args)
    success = _deliver_markdown_files_and_images(
        kind="evening",
        trade_date=args.date,
        context=context,
        text_files=[
            (summary_path, "美股市场盘前 / 亚洲市场盘后", "美股市场盘前 / 亚洲市场盘后"),
            (review_path, "完整盘后数据", "完整盘后数据"),
        ],
        image_paths=chart_paths,
        artifacts=artifacts,
        webhook_enabled_env="EVENING_SEND_WEBHOOK",
        signal_date=signal_date,
    )
    return 0 if success else 1


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deliver deterministic A-share reports")
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--chat-id", help="Feishu chat ID override")
    common.add_argument("--user-id", help="Feishu user open_id override")
    common.add_argument("--hermes-target", help="Hermes send target, e.g. feishu:oc_xxx")
    common.add_argument("--hermes-cli", help="hermes CLI path override")
    common.add_argument("--lark-cli", help="lark-cli path override")
    morning = sub.add_parser("morning", parents=[common], help="Deliver morning report")
    morning.add_argument("--report", required=True, help="Morning markdown report path")
    morning.add_argument("--manifest", help="Morning manifest JSON path")
    evening = sub.add_parser("evening", parents=[common], help="Deliver evening report")
    evening.add_argument("--date", required=True, help="Trade date YYYYMMDD")
    evening.add_argument("--out-dir", default="out/a_share_daily", help="A-share report output dir")
    evening.add_argument(
        "--summary-out", required=True, help="Evening summary markdown output path"
    )
    evening.add_argument("--review", required=True, help="Evening review markdown path")
    evening.add_argument("--review-json", required=True, help="Evening review JSON path")
    evening.add_argument("--news", required=True, help="Evening news JSON path")
    evening.add_argument("--manifest", required=True, help="Evening manifest JSON path")
    evening.add_argument("--chart", action="append", help="Chart image path; may be repeated")
    args = parser.parse_args(argv)
    if args.command == "morning":
        return deliver_morning(args)
    if args.command == "evening":
        return deliver_evening(args)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(run())
