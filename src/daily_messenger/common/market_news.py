"""Shared market-news metadata and parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketNewsSpec:
    market: str
    label: str
    timezone: ZoneInfo
    close_hour: int
    close_minute: int
    scope: str


NEWS_TAG_PATTERN = re.compile(r"<news>(.*?)</news>", re.IGNORECASE | re.DOTALL)

AI_NEWS_MARKET_SPECS: tuple[MarketNewsSpec, ...] = (
    MarketNewsSpec(
        market="us",
        label="美股",
        timezone=ZoneInfo("America/New_York"),
        close_hour=16,
        close_minute=0,
        scope="美国股市",
    ),
    MarketNewsSpec(
        market="jp",
        label="日股",
        timezone=ZoneInfo("Asia/Tokyo"),
        close_hour=15,
        close_minute=0,
        scope="日本股市",
    ),
    MarketNewsSpec(
        market="hk",
        label="港股",
        timezone=ZoneInfo("Asia/Hong_Kong"),
        close_hour=16,
        close_minute=0,
        scope="香港股市",
    ),
    MarketNewsSpec(
        market="kr",
        label="韩股",
        timezone=ZoneInfo("Asia/Seoul"),
        close_hour=15,
        close_minute=30,
        scope="韩国股市",
    ),
    MarketNewsSpec(
        market="cn",
        label="A 股",
        timezone=ZoneInfo("Asia/Shanghai"),
        close_hour=15,
        close_minute=0,
        scope="中国内地 A 股市场",
    ),
    MarketNewsSpec(
        market="gold",
        label="黄金",
        timezone=ZoneInfo("America/New_York"),
        close_hour=17,
        close_minute=0,
        scope="国际黄金市场",
    ),
)


def extract_news_section(text: str) -> str:
    """Extract model output inside ``<news>`` tags when present."""
    if not text:
        return ""
    sections = [match.strip() for match in NEWS_TAG_PATTERN.findall(text) if match]
    if sections:
        combined = "\n".join(section.strip() for section in sections if section.strip())
        return combined.strip()
    return text.strip()
