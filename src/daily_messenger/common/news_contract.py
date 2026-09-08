"""Structured market-news contract helpers.

LLM/search providers may be used to find candidate news, but downstream
reports should consume only validated, attributed items.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

VALID_CATEGORIES = {"policy", "company", "macro", "sector"}
DEFAULT_CATEGORY = "macro"
MAX_SUMMARY_CHARS = 180

_NEWS_TAG_PATTERN = re.compile(r"<news(?:_json)?>(.*?)</news(?:_json)?>", re.I | re.S)
_FENCED_JSON_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.I | re.S)


def _clean_text(value: Any, max_len: int = 240) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().split())
    return text[:max_len].rstrip()


def _valid_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("https://") or lowered.startswith("http://")


def _coerce_items(raw: Any) -> list[Mapping[str, Any]]:
    if isinstance(raw, Mapping):
        candidate = raw.get("items") or raw.get("news") or raw.get("results")
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, Mapping)]
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, Mapping)]
    return []


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for pattern in (_NEWS_TAG_PATTERN, _FENCED_JSON_PATTERN):
        candidates.extend(match.strip() for match in pattern.findall(text) if match.strip())
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)
    return candidates


def parse_news_items_from_text(text: str) -> list[Mapping[str, Any]]:
    """Extract ``items`` from JSON embedded in provider output.

    Supports raw JSON, fenced JSON, and ``<news>...</news>`` wrappers for
    backwards-compatible prompts.
    """
    if not text:
        return []
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        items = _coerce_items(parsed)
        if items:
            return items
    return []


def normalize_news_items(
    raw_items: Sequence[Mapping[str, Any]],
    *,
    market: str,
    label: str = "",
    fallback_published_at: str = "",
    max_items: int = 5,
    require_url: bool = True,
) -> tuple[list[dict[str, str]], list[str]]:
    """Validate and normalize news items.

    Required fields for strict report consumption are title, summary, source,
    url, and published_at.  Items without a URL are rejected by default because
    they are not auditable enough for automated reports.
    """
    normalized: list[dict[str, str]] = []
    errors: list[str] = []
    for index, item in enumerate(raw_items, start=1):
        title = _clean_text(item.get("title"), 120)
        summary = _clean_text(item.get("summary"), MAX_SUMMARY_CHARS)
        source = _clean_text(item.get("source"), 80)
        url = _clean_text(item.get("url"), 300)
        published_at = _clean_text(item.get("published_at") or fallback_published_at, 40)
        category = _clean_text(item.get("category"), 40).lower() or DEFAULT_CATEGORY
        if category not in VALID_CATEGORIES:
            category = DEFAULT_CATEGORY

        missing = [
            field
            for field, value in (
                ("title", title),
                ("summary", summary),
                ("source", source),
                ("published_at", published_at),
            )
            if not value
        ]
        if require_url and (not url or not _valid_url(url)):
            missing.append("url")
        if missing:
            errors.append(f"item_{index}: missing/invalid {','.join(missing)}")
            continue

        normalized.append(
            {
                "market": market,
                "label": label,
                "category": category,
                "title": title,
                "summary": summary,
                "source": source,
                "url": url,
                "published_at": published_at,
            }
        )
        if len(normalized) >= max_items:
            break
    return normalized, errors


def render_news_text(items: Sequence[Mapping[str, Any]]) -> str:
    """Render validated items as compact Markdown for legacy consumers."""
    lines: list[str] = []
    for item in items:
        category = _clean_text(item.get("category"), 40)
        title = _clean_text(item.get("title"), 120)
        summary = _clean_text(item.get("summary"), MAX_SUMMARY_CHARS)
        source = _clean_text(item.get("source"), 80)
        url = _clean_text(item.get("url"), 300)
        if not (title and summary and source and url):
            continue
        lines.append(f"- [{category}] {summary}（{source}: [{title}]({url})）")
    return "\n".join(lines)
