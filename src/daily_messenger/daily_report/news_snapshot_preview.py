"""Render clearly unreviewed local previews; never create publication approval."""

from __future__ import annotations

import re
from decimal import Decimal
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
    scales = {"K": 1000, "M": 1000000, "B": 1000000000, "万": 10000, "亿": 100000000}

    def scaled(match: re.Match[str]) -> str:
        value = Decimal(match[1]) * scales[match[2]]
        return format(value.normalize(), "f")

    text = re.sub(r"(\d+(?:\.\d+)?)([KMB万亿])(?![A-Za-z])", scaled, text)
    tokens = {t.lstrip("+") for t in re.findall(r"[+-]?\d+(?:\.\d+)?(?:-\d+)?%?", text)}
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    tokens.update(str(i) for i, word in enumerate(words) if re.search(r"\b" + word + r"\b", text))
    for year in re.findall(
        r"(?:FY|Jan-|Feb-|Mar-|Apr-|May-|Jun-|Jul-|Aug-|Sep-|Oct-|Nov-|Dec-)(\d{2})\b", text
    ):
        tokens.add(str(2000 + int(year)))
    return tokens


def _entries(source: dict[str, Any], edited: dict[str, Any]) -> list[dict[str, Any]]:
    if "items" not in edited:
        return [edited]
    items = edited["items"]
    if "text" in edited or "block_ids" in edited:
        raise ValueError("editorial cannot mix text and items")
    if not isinstance(items, list) or not items or len(items) > 100:
        raise ValueError("editorial items must be nonempty and bounded")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("editorial items must be objects")
    items = cast(list[dict[str, Any]], items)
    if not all(
        isinstance(item.get("block_ids"), list)
        and all(isinstance(i, str) for i in item["block_ids"])
        for item in items
    ):
        raise ValueError("editorial contains invalid block references")
    refs = [i for item in items for i in item.get("block_ids", [])]
    expected = [block["id"] for block in source["blocks"]]
    if list(dict.fromkeys(refs)) != expected:
        raise ValueError("itemized source coverage or order mismatch")
    positions = [expected.index(i) for i in refs]
    if positions != sorted(positions):
        raise ValueError("itemized source order mismatch")
    if source["key"] in {"gainers", "losers"} and [item.get("block_ids") for item in items] != [
        [i] for i in expected
    ]:
        raise ValueError("movers require one item per source block")
    return items


def _validate_entry(blocks: dict[str, Any], entry: dict[str, Any]) -> str:
    ids, text = entry.get("block_ids"), entry.get("text")
    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(i, str) and i in blocks for i in ids)
    ):
        raise ValueError("editorial contains missing or foreign block references")
    if not isinstance(text, str) or not text.strip() or len(text) > 5000:
        raise ValueError("editorial text must be nonempty and bounded")
    original = " ".join(blocks[i]["text"] for i in ids)
    allowed = _numeric_tokens(original)
    if ids == ["market-title"] and original.startswith("US equities finish lower:"):
        signed = re.sub(r"\((\d+(?:\.\d+)?%)\)", r"-\1", original)
        allowed.update(_numeric_tokens(signed))
    if not _numeric_tokens(text) <= allowed:
        raise ValueError("editorial introduces changed numeric tokens")
    for ticker in re.findall(r"^[+-]\d+(?:\.\d+)?% ([A-Z]+)\b", original):
        if not re.search(r"\b" + ticker + r"\b", text):
            raise ValueError("editorial omits mover ticker")
    return text


def validate_editorial(snapshot: dict[str, Any], editorial: dict[str, Any]) -> list[list[str]]:
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
        texts.append([_validate_entry(blocks, entry) for entry in _entries(source, edited)])
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
            entries = editorial["sections"][index] if editorial is not None else {}
            if "items" not in entries:
                rows.append(_safe(texts[index][0]))
            else:
                number = 0
                for entry, text in zip(entries["items"], texts[index], strict=True):
                    if index == 0 and entry["block_ids"] == ["market-title"]:
                        rows.extend([_safe(text), ""])
                    else:
                        number += 1
                        rows.extend([f"{number}、" + _safe(text), ""])
        rows.append("")
    rows.append(
        "Format and numeric-token checks do not certify meaning, units, causality or source accuracy."
    )
    return "\n".join(rows) + "\n"
