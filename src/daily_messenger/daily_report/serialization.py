"""JSON serialization for daily report artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def dumps_json(value: Any) -> str:
    return json.dumps(value, default=_default, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(dumps_json(value), encoding="utf-8")


def content_digest(payload: dict) -> str:
    """Hash parsed or serialized report payloads through the legacy contract."""

    def normalize(value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {name: normalize(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [normalize(item, key) for item in value]
        if isinstance(value, str) and key in {
            "as_of",
            "generated_at",
            "source_time",
            "retrieved_at",
        }:
            return datetime.fromisoformat(value)
        return value

    content = normalize(payload | {"content_hash": None})
    return hashlib.sha256(
        json.dumps(content, default=str, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
