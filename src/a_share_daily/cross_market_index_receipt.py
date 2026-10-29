"""Consume operational index receipts without provider access or owner imports."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

CODES = {"HSI": "^HSI", "N225": "^N225", "KS11": "^KS11"}
PROTOCOL = "overseas-index-operational-v1"


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("naive receipt timestamp")
    return result


def _read(path: Path, root: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("receipt path outside permitted root")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("receipt file too large")
    return raw


def _quote(code: str, source: dict, receipt: dict, path: Path) -> dict:
    from .cross_market import _equity_sessions

    if source["status"] != "ok" or source["api"] != "index_global":
        raise ValueError("source unavailable")
    if source["provider"] != "tushare-compatible":
        raise ValueError("unexpected provider")
    if not (
        _time(receipt["started_utc"])
        <= _time(source["request_started_utc"])
        <= _time(source["request_completed_utc"])
        <= _time(receipt["completed_utc"])
    ):
        raise ValueError("invalid source receipt time")
    filename = source["file"]
    if not isinstance(filename, str) or filename != f"{code}.csv":
        raise ValueError("invalid source filename")
    raw = _read(path.parent / filename, path.parent, 4_000_000)
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("source hash mismatch")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    if type(source["rows"]) is not int or source["rows"] != len(rows):
        raise ValueError("source row count mismatch")
    _, target, preceding = _equity_sessions(CODES[code], receipt["requested_date"])
    target_day, previous_day = target.strftime("%Y%m%d"), preceding.strftime("%Y%m%d")
    values = {}
    for row in rows:
        day = row["trade_date"]
        if datetime.strptime(day, "%Y%m%d").strftime("%Y%m%d") != day:
            raise ValueError("invalid source date")
        if row["ts_code"] != code or day in values or day > target_day:
            raise ValueError("wrong code, duplicate or future session")
        close = float(row["close"])
        if not math.isfinite(close) or close <= 0:
            raise ValueError("invalid source close")
        values[day] = close
    if sorted(values) != source["source_dates"]:
        raise ValueError("source dates mismatch")
    if target_day not in values or previous_day not in values:
        raise ValueError("missing target or preceding session")
    return {
        "close": round(values[target_day], 2),
        "pct_chg": round((values[target_day] / values[previous_day] - 1) * 100, 2),
        "as_of_date": target.isoformat(),
        "source": "tushare-compatible",
        "source_url": "https://tushare.pro/document/2?doc_id=211",
        "received_at": source["request_completed_utc"],
        "source_sha256": source["sha256"],
        "route_host": source.get("route_host"),
        "receipt_path": str(path.resolve()),
    }


def _validate_receipt(raw: bytes, day: str, observed_at: datetime) -> dict:
    receipt = json.loads(raw)
    if receipt["protocol"] != PROTOCOL or receipt["requested_date"] != day:
        raise ValueError("protocol or requested date mismatch")
    if receipt["status"] not in {"complete", "partial", "failed"}:
        raise ValueError("invalid receipt status")
    if not _time(receipt["started_utc"]) <= _time(receipt["completed_utc"]) <= observed_at:
        raise ValueError("receipt unavailable at observation cutoff")
    if not isinstance(receipt["sources"], dict):
        raise ValueError("invalid receipt sources")
    return receipt


def recover_indices(data: dict, receipt_path: Path, *, root: Path, observed_at: datetime) -> dict:
    """Return a copy with verified missing quotes; all invalid inputs fail closed."""
    from .cross_market import _annotate_freshness, _equity_sessions
    from .global_leadlag import aggregate_concept_signals
    from .overseas_context import local_time, observation_cutoff

    result = copy.deepcopy(data)
    diagnostic: dict[str, Any] = {"recovered": [], "rejections": {}, "attempts": {}}
    result["_index_recovery"] = diagnostic
    try:
        raw = _read(receipt_path, root, 1_000_000)
        receipt = _validate_receipt(raw, data["date"], observed_at)
        diagnostic["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
        diagnostic["observed_at"] = observed_at.isoformat()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        diagnostic["rejections"]["receipt"] = type(exc).__name__
        return result
    quotes = result.setdefault("us_stocks", {})
    for code, symbol in CODES.items():
        old = quotes.get(symbol, {})
        _, target, _ = _equity_sessions(symbol, data["date"])
        if (
            isinstance(old, dict)
            and not old.get("error")
            and old.get("as_of_date") == target.isoformat()
            and isinstance(old.get("close"), (int, float))
            and math.isfinite(old["close"])
            and old["close"] > 0
        ):
            continue
        if code not in receipt["sources"]:
            continue
        try:
            quote = _quote(code, receipt["sources"][code], receipt, receipt_path)
        except (OSError, ValueError, KeyError, TypeError, OverflowError, csv.Error) as exc:
            diagnostic["rejections"][symbol] = type(exc).__name__
            continue
        diagnostic["attempts"][symbol] = old
        diagnostic["recovered"].append(symbol)
        quote["fallback_reason"] = (
            old.get("error", "missing or stale quote") if isinstance(old, dict) else "invalid quote"
        )
        quote["receipt_sha256"] = diagnostic["receipt_sha256"]
        quotes[symbol] = quote
        for field in ("errors", "_freshness_warnings"):
            result[field] = [
                item for item in result.get(field, []) if not str(item).startswith(f"{symbol}:")
            ]
    if diagnostic["recovered"]:
        result["global_lead_lag"] = aggregate_concept_signals(
            quotes,
            decision_at=observation_cutoff(local_time(observed_at).strftime("%Y%m%d"), observed_at),
        )
        result["concept_mapping"] = result["global_lead_lag"]
    return _annotate_freshness(result, data["date"])
