#!/usr/bin/env python3
"""Thin CLI wrapper for structured AI market-news fetching.

Usage:
    uv run python scripts/fetch_ai_market_news.py
    uv run python scripts/fetch_ai_market_news.py --markets jp,kr
    uv run python scripts/fetch_ai_market_news.py --json-out /tmp/n.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from daily_messenger.common.market_news import AI_NEWS_MARKET_SPECS
from daily_messenger.etl.fetchers.ai_news import fetch_market_news_payload

DEFAULT_MARKETS = ("cn", "jp", "kr", "us")
KNOWN_MARKETS = {spec.market for spec in AI_NEWS_MARKET_SPECS}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parse_markets(raw: str) -> list[str]:
    markets = [market.strip().lower() for market in raw.split(",") if market.strip()]
    unknown = [market for market in markets if market not in KNOWN_MARKETS]
    if unknown:
        raise ValueError(f"unknown market code(s): {', '.join(unknown)}")
    return markets


def fetch_news(markets: list[str]) -> dict[str, Any]:
    default_api_keys = PROJECT_ROOT / "api_keys.json"
    if (
        "API_KEYS" not in os.environ
        and "API_KEYS_PATH" not in os.environ
        and default_api_keys.exists()
    ):
        os.environ["API_KEYS_PATH"] = str(default_api_keys)
    return fetch_market_news_payload(markets)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _market_label(market: str) -> str:
    for spec in AI_NEWS_MARKET_SPECS:
        if spec.market == market:
            return spec.label
    return market


def _json_from_stdout(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def fetch_news_per_market(
    markets: list[str],
    *,
    market_timeout: float,
    retries: int,
    sleep_seconds: float,
) -> dict[str, Any]:
    """Fetch markets independently so one slow provider call does not block all markets."""
    script = Path(__file__).resolve()
    merged_markets: dict[str, dict[str, Any]] = {}
    providers: list[dict[str, Any]] = []
    provider = ""
    model = ""

    for market in markets:
        attempts: list[dict[str, Any]] = []
        selected_entry: dict[str, Any] | None = None
        selected_payload: dict[str, Any] = {}

        for attempt in range(1, max(retries, 0) + 2):
            command = [sys.executable, str(script), "--markets", market]
            started = time.monotonic()
            try:
                result = subprocess.run(
                    command,
                    cwd=str(PROJECT_ROOT),
                    text=True,
                    capture_output=True,
                    timeout=market_timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                attempts.append(
                    {
                        "attempt": attempt,
                        "ok": False,
                        "error": f"timeout after {market_timeout:.0f}s",
                    }
                )
            else:
                elapsed = round(time.monotonic() - started, 2)
                payload = _json_from_stdout(result.stdout or "")
                market_payload = payload.get("markets", {}) if isinstance(payload, dict) else {}
                entry = market_payload.get(market) if isinstance(market_payload, dict) else None
                entry = entry if isinstance(entry, dict) else {}
                ok = result.returncode == 0 and bool(entry.get("news_text"))
                error = str(entry.get("error") or "").strip()
                if result.returncode != 0 and not error:
                    error = (result.stderr or result.stdout or "").strip()[:500]
                attempts.append(
                    {
                        "attempt": attempt,
                        "ok": ok,
                        "returncode": result.returncode,
                        "elapsed_seconds": elapsed,
                        **({"error": error} if error else {}),
                    }
                )
                selected_payload = payload or selected_payload
                selected_entry = entry or selected_entry
                if ok:
                    break

            if attempt <= max(retries, 0) and sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if selected_payload:
            provider = provider or str(selected_payload.get("provider") or "")
            model = model or str(selected_payload.get("model") or "")
            if not providers and isinstance(selected_payload.get("providers"), list):
                providers = list(selected_payload.get("providers") or [])

        entry = dict(selected_entry or {})
        entry.setdefault("market", market)
        entry.setdefault("label", _market_label(market))
        if not entry.get("news_text"):
            last_error = next(
                (str(item.get("error")) for item in reversed(attempts) if item.get("error")),
                "AI market news fetch did not return news_text",
            )
            entry["error"] = last_error
        entry["attempts"] = attempts
        merged_markets[market] = entry

    return {
        "per_market": True,
        "provider": provider,
        "model": model,
        "providers": providers,
        "markets_requested": markets,
        "markets": merged_markets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch structured AI market news")
    parser.add_argument(
        "--markets",
        default=",".join(DEFAULT_MARKETS),
        help=f"Market codes (default: {','.join(DEFAULT_MARKETS)})",
    )
    parser.add_argument("--json-out", help="Write JSON to file")
    parser.add_argument(
        "--per-market",
        action="store_true",
        help="Fetch each market in a separate subprocess with independent timeout/retries.",
    )
    parser.add_argument(
        "--market-timeout",
        type=float,
        default=_env_float("AI_NEWS_MARKET_TIMEOUT", 45.0),
        help="Timeout in seconds for each market attempt in --per-market mode.",
    )
    parser.add_argument(
        "--market-retries",
        type=int,
        default=_env_int("AI_NEWS_MARKET_RETRIES", 1),
        help="Retries per market after the first attempt in --per-market mode.",
    )
    parser.add_argument(
        "--market-sleep",
        type=float,
        default=_env_float("AI_NEWS_MARKET_SLEEP_SECONDS", 3.0),
        help="Sleep seconds between per-market retries.",
    )
    args = parser.parse_args()

    try:
        markets = _parse_markets(args.markets)
    except ValueError as exc:
        parser.error(str(exc))

    if args.per_market:
        data = fetch_news_per_market(
            markets,
            market_timeout=max(args.market_timeout, 1.0),
            retries=max(args.market_retries, 0),
            sleep_seconds=max(args.market_sleep, 0.0),
        )
    else:
        data = fetch_news(markets)
    json_text = json.dumps(data, ensure_ascii=False, indent=2)

    if args.json_out:
        Path(args.json_out).expanduser().write_text(json_text, encoding="utf-8")
        markets_payload = data.get("markets", {})
        market_entries = markets_payload.values() if isinstance(markets_payload, dict) else []
        ok = sum(1 for item in market_entries if isinstance(item, dict) and "news_text" in item)
        print(f"AI market news: {ok}/{len(markets)} OK")
    else:
        print(json_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
