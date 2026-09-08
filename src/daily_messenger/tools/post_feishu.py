#!/usr/bin/env python3
"""Send Feishu notification using incoming webhook."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

from daily_messenger.common.logging import log, setup_logger


def _read_file(path: str | None) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    data = file_path.read_text(encoding="utf-8")
    return data.strip()


def _sign_if_needed(secret: str | None) -> dict[str, str]:
    if not secret:
        return {}
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    key = secret.encode("utf-8")
    hmac_code = hmac.new(key, string_to_sign.encode("utf-8"), digestmod=hashlib.sha256)
    sign = base64.b64encode(hmac_code.digest()).decode("utf-8")
    return {"timestamp": timestamp, "sign": sign}


def _split_summary_sections(summary: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    for raw_line in summary.splitlines():
        if raw_line.strip():
            current.append(raw_line.rstrip())
            continue
        if current:
            sections.append("\n".join(current))
            current = []
    if current:
        sections.append("\n".join(current))
    if not sections:
        sections.append("今日暂无摘要")
    return sections


def _build_payload(args: argparse.Namespace, summary: str, card: str | None) -> dict[str, Any]:
    if args.mode == "interactive":
        if not card:
            raise ValueError("需要提供 --card 文件以发送互动卡片")
        return {"msg_type": "interactive", "card": json.loads(card)}

    # post 模式
    sections = _split_summary_sections(summary)
    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": args.title or "内参播报",
                    "content": [
                        [
                            {
                                "tag": "text",
                                "text": section if section.endswith("\n") else section + "\n",
                            }
                        ]
                        for section in sections
                    ],
                }
            }
        },
    }


def _normalize_channel(value: str | None) -> str:
    if not value:
        return "daily"
    lowered = value.lower()
    if lowered in {"daily", "report"}:
        return "daily"
    if lowered in {"alerts", "alert"}:
        return "alerts"
    raise ValueError(f"未知频道 {value!r}，请使用 daily 或 alerts")


def _split_webhooks(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _filter_disabled_webhooks(webhooks: list[str], channel: str) -> list[str]:
    suffix = channel.upper()
    disabled = set(_split_webhooks(os.getenv("FEISHU_WEBHOOK_DISABLED")))
    disabled.update(_split_webhooks(os.getenv(f"FEISHU_WEBHOOK_{suffix}_DISABLED")))
    if not disabled:
        return webhooks
    return [webhook for webhook in webhooks if webhook not in disabled]


def _resolve_credentials(
    channel: str,
    explicit_webhook: str | None,
    explicit_secret: str | None,
) -> tuple[list[str], str | None]:
    if explicit_webhook:
        return _split_webhooks(explicit_webhook), explicit_secret

    suffix = channel.upper()
    webhooks = _split_webhooks(os.getenv(f"FEISHU_WEBHOOK_{suffix}"))
    secret = explicit_secret or os.getenv(f"FEISHU_SECRET_{suffix}")
    return _filter_disabled_webhooks(webhooks, channel), secret


def _send_payload(webhook: str, payload: dict[str, Any], logger: logging.Logger) -> bool:
    resp = requests.post(webhook, json=payload, timeout=10)
    if resp.status_code != 200:
        log(
            logger,
            logging.ERROR,
            "feishu_http_error",
            status_code=resp.status_code,
            response=resp.text[:500],
        )
        return False

    body = (
        resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    )
    if body.get("StatusCode", 0) != 0:
        log(logger, logging.ERROR, "feishu_business_error", response=body)
        return False
    return True


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Push message to Feishu webhook")
    from pathlib import Path as _P

    base_dir = _P(__file__).resolve().parents[3]
    out_dir = base_dir / "out"
    parser.add_argument("--channel", default="daily", help="消息频道（daily 或 alerts）")
    parser.add_argument("--webhook", help="飞书自定义机器人 Webhook（覆盖 channel 推断）")
    parser.add_argument(
        "--summary",
        default=str(out_dir / "digest_summary.txt"),
        help="摘要文本路径（默认 out/digest_summary.txt）",
    )
    parser.add_argument(
        "--card",
        default=str(out_dir / "digest_card.json"),
        help="互动卡片 JSON 文件路径（默认 out/digest_card.json）",
    )
    parser.add_argument("--secret", help="签名密钥（覆盖 channel 推断）")
    parser.add_argument("--mode", choices=["interactive", "post"], default=None)
    parser.add_argument("--title", help="备用标题（post 模式使用）")
    args = parser.parse_args(argv)

    logger = setup_logger("feishu")

    try:
        channel = _normalize_channel(args.channel)
    except ValueError as exc:
        parser.error(str(exc))

    webhooks, secret = _resolve_credentials(channel, args.webhook, args.secret)

    summary = _read_file(args.summary)
    card_text = _read_file(args.card)
    if args.mode is None:
        card_path = _P(args.card) if args.card else None
        args.mode = "interactive" if card_path and card_path.exists() else "post"
    card = card_text or None

    payload = _build_payload(args, summary, card)
    payload.update(_sign_if_needed(secret))

    if not webhooks:
        log(logger, logging.INFO, "feishu_skip_missing_webhook", channel=channel)
        return 0

    results = [_send_payload(webhook, payload, logger) for webhook in webhooks]
    if not all(results):
        return 1

    log(
        logger,
        logging.INFO,
        "feishu_push_completed",
        channel=channel,
        mode=args.mode,
        has_card=bool(card),
        summary_length=len(summary.splitlines()),
        webhook_count=len(webhooks),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
