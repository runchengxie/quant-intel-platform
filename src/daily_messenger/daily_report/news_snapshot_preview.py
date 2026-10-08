"""Render clearly unreviewed local previews; never create publication approval."""

from __future__ import annotations

import re
from typing import Any, cast

from .news_snapshot_parse import SECTION_KEYS

TITLES = {
    "en-US": (
        "Market performance",
        "Market drivers",
        "Company and industry news",
        "Macro and Federal Reserve",
        "Notable gainers",
        "Notable decliners",
    ),
    "zh-CN": (
        "一、市场表现",
        "二、市场主线",
        "三、公司与行业动态",
        "四、经济数据与美联储",
        "五、重点上涨个股",
        "六、重点下跌个股",
    ),
}


def _safe(text: str) -> str:
    # Source HTML is already stripped; disable active Markdown in retained text.
    return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", text).replace("\n", " ")


def _numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"[+-]?\d+(?:\.\d+)?(?:-\d+)?%?", text))


def validate_editorial(snapshot: dict[str, Any], editorial: dict[str, Any]) -> list[str]:
    if editorial.get("source_sha256") != snapshot["source_sha256"]:
        raise ValueError("editorial source hash mismatch")
    sections = editorial.get("sections")
    if (
        not isinstance(sections, list)
        or not all(isinstance(s, dict) for s in sections)
        or [s.get("key") for s in sections] != list(SECTION_KEYS)
    ):
        raise ValueError("editorial requires all six ordered sections")
    sections = cast(list[dict[str, Any]], sections)
    texts = []
    for source, edited in zip(snapshot["sections"], sections, strict=True):
        blocks = {block["id"]: block for block in source["blocks"]}
        ids, text = edited.get("block_ids"), edited.get("text")
        if (
            not isinstance(ids, list)
            or not ids
            or not all(isinstance(i, str) and i in blocks for i in ids)
        ):
            raise ValueError("editorial contains missing or foreign block references")
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            raise ValueError("editorial text must be nonempty and bounded")
        original = " ".join(blocks[i]["text"] for i in ids)
        if not _numeric_tokens(text) <= _numeric_tokens(original):
            raise ValueError("editorial introduces changed numeric tokens")
        texts.append(text)
    return texts


def render_preview(
    snapshot: dict[str, Any], *, locale: str = "en-US", editorial: dict[str, Any] | None = None
) -> str:
    if locale not in TITLES:
        raise ValueError("unsupported preview locale")
    rows = [
        "# NOT FOR PUBLICATION / 待审核本地预览",
        "",
        f"Market date: {snapshot['market_date']}",
        f"Status: {snapshot['status']}; publication time unresolved; no source approval.",
        f"Capture: {snapshot['captured_at']} ({snapshot['capture_mode']})",
        f"Source: {snapshot['source_url']}",
        "",
    ]
    if snapshot["issues"]:
        if editorial is not None:
            raise ValueError("quarantined snapshots cannot accept editorial text")
        return "\n".join([*rows, "Quarantined: " + ", ".join(snapshot["issues"]), ""])
    texts = validate_editorial(snapshot, editorial) if editorial is not None else None
    for index, section in enumerate(snapshot["sections"]):
        rows.extend(["## " + TITLES[locale][index], ""])
        if texts is None:
            rows.extend("- " + _safe(block["text"]) for block in section["blocks"])
        else:
            rows.append(_safe(texts[index]))
        rows.append("")
    rows.append(
        "Format and numeric-token checks do not certify meaning, units, causality or source accuracy."
    )
    return "\n".join(rows) + "\n"
