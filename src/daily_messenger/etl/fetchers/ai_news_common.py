"""Shared constants, dataclasses and provider-agnostic helpers for the fetcher.

This module is a pure physical split-out of ``ai_news.py``. It holds the
module-level constants, dataclasses and provider-agnostic helper functions
(date helpers, source-URL/ relevance filtering, the market prompt builder and
the key-queue builder) so that the provider-specific and orchestration
submodules can import from a single, small source. Provider settings resolution
lives in ``ai_news_settings_chain``; provider HTTP calls live in the per-provider
modules.
"""

from __future__ import annotations

import os
import random
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from daily_messenger.common.market_news import (
    MarketNewsSpec as _MarketNewsSpec,
)
from daily_messenger.etl.config import (
    AI_NEWS_PROVIDER_ALIYUN,
    AI_NEWS_PROVIDER_GEMINI,
    AI_NEWS_PROVIDER_GLM,
)
from daily_messenger.etl.http import (
    sleep_exact as _sleep_exact,
)

CHINA_TZ = ZoneInfo("Asia/Shanghai")
THROTTLE_DISABLED = os.getenv("DM_DISABLE_THROTTLE", "").lower() in {"1", "true", "yes"}


def _sleep(seconds: float) -> None:
    if seconds <= 0 or THROTTLE_DISABLED:
        return
    _sleep_exact(seconds)


@dataclass
class _AiNewsSettings:
    provider: str
    model: str
    keys: list[tuple[str, str]]
    enable_network: bool
    direct_connection: bool
    timeout: float
    extra_instructions: str = ""
    thinking: str | None = None
    base_url: str | None = None
    search_strategy: str | None = None


@dataclass(frozen=True)
class _ParsedMarketNews:
    news_section: str
    items: list[dict[str, Any]]
    item_errors: list[str]
    summary: str


AI_NEWS_PROVIDER_META = {
    AI_NEWS_PROVIDER_GLM: {"source": "glm", "provider": "zhipu_glm"},
    AI_NEWS_PROVIDER_ALIYUN: {"source": "aliyun", "provider": "aliyun_bailian"},
    AI_NEWS_PROVIDER_GEMINI: {"source": "gemini", "provider": "google_gemini"},
}
GLM_CHAT_COMPLETIONS_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MAX_RETRIES = 3
GLM_BACKOFF_START = 0.8
GLM_BACKOFF_FACTOR = 2.0
GLM_BACKOFF_JITTER = 0.35
GLM_RETRY_STATUS_CODES = (408, 409, 425, 500, 502, 503, 504)

GEMINI_MAX_RETRIES = 3
GEMINI_BACKOFF_START = 0.8
GEMINI_BACKOFF_FACTOR = 2.0
GEMINI_BACKOFF_JITTER = 0.35
GEMINI_INTER_MARKET_DELAY_RANGE = (0.8, 1.6)

ALIYUN_MAX_RETRIES = 3
ALIYUN_BACKOFF_START = 0.8
ALIYUN_BACKOFF_FACTOR = 2.0
ALIYUN_BACKOFF_JITTER = 0.35

_PLACEHOLDER_SOURCE_DOMAINS = {
    "example.com",
    "www.example.com",
    "example.org",
    "www.example.org",
    "example.net",
    "www.example.net",
}

_MARKET_RELEVANCE_TERMS = {
    "jp": (
        "日本",
        "日股",
        "日经",
        "日經",
        "东京",
        "東京",
        "nikkei",
        "topix",
        "tokyo",
        "kioxia",
        "铠侠",
        "鎧俠",
        "东京电子",
        "東京電子",
        "tokyo electron",
        "advantest",
        "爱德万",
        "softbank",
        "软银",
        "sony",
        "toyota",
        "8035.t",
        "6857.t",
        "6723.t",
        "6920.t",
        "8035",
        "6857",
        "6723",
        "6920",
    ),
    "kr": (
        "韩国",
        "韓国",
        "韩股",
        "韓股",
        "韩综指",
        "韩国综合指数",
        "kospi",
        "kosdaq",
        "samsung",
        "三星",
        "sk hynix",
        "sk海力士",
        "sk 海力士",
        "海力士",
        "hyundai",
        "现代汽车",
        "lg",
        "005930.ks",
        "000660.ks",
        "042700.ks",
        "005930",
        "000660",
        "042700",
    ),
}


def _business_day_on_or_before(day: datetime) -> datetime:
    candidate = day
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _resolve_market_trading_date(now_utc: datetime, spec: _MarketNewsSpec) -> datetime:
    local_now = now_utc.astimezone(spec.timezone)
    candidate = datetime(
        local_now.year,
        local_now.month,
        local_now.day,
        0,
        0,
        0,
        tzinfo=spec.timezone,
    )
    close_dt = datetime(
        local_now.year,
        local_now.month,
        local_now.day,
        spec.close_hour,
        spec.close_minute,
        0,
        tzinfo=spec.timezone,
    )
    if local_now < close_dt:
        candidate -= timedelta(days=1)
    return _business_day_on_or_before(candidate)


def _format_cn_date(day: datetime | date) -> str:
    return day.strftime("%Y年%m月%d日")


def _is_placeholder_source_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return True
    return host.lower() in _PLACEHOLDER_SOURCE_DOMAINS


def _market_relevance_error(item: Mapping[str, Any], market: str) -> str | None:
    terms = _MARKET_RELEVANCE_TERMS.get(market)
    if not terms:
        return None
    haystack = " ".join(
        str(item.get(field) or "") for field in ("title", "summary", "source", "url")
    ).lower()
    if any(term.lower() in haystack for term in terms):
        return None
    title = str(item.get("title") or "").strip() or "untitled"
    return f"{title}: missing explicit {market.upper()} market relevance"


def _filter_market_relevant_items(
    items: Sequence[Mapping[str, Any]],
    *,
    market: str,
) -> tuple[list[dict[str, str]], list[str]]:
    filtered: list[dict[str, str]] = []
    errors: list[str] = []
    for index, item in enumerate(items, start=1):
        url = str(item.get("url") or "")
        if _is_placeholder_source_url(url):
            errors.append(f"item_{index}: placeholder source URL")
            continue
        relevance_error = _market_relevance_error(item, market)
        if relevance_error:
            errors.append(f"item_{index}: {relevance_error}")
            continue
        filtered.append({str(key): str(value) for key, value in item.items()})
    return filtered, errors


def _build_market_prompt(
    spec: _MarketNewsSpec,
    target_day: datetime,
    now_beijing: datetime,
    settings: _AiNewsSettings,
) -> str:
    target_iso = target_day.date().isoformat()
    target_cn = _format_cn_date(target_day.date())
    now_cn = now_beijing.strftime("%Y年%m月%d日 %H:%M")
    extra = f"\n{settings.extra_instructions.strip()}" if settings.extra_instructions else ""
    market_guardrail = {
        "jp": (
            "每条日股新闻必须明确提到日本市场、日经/TOPIX、东京交易所上市公司"
            "或日本政策；只谈全球宏观、原油、地缘或中国/美国公司而没有日本市场"
            "传导证据的内容必须丢弃。"
        ),
        "kr": (
            "每条韩股新闻必须明确提到韩国市场、KOSPI/KOSDAQ、三星电子、SK海力士"
            "等韩国上市公司或韩国政策；只谈全球宏观、原油、地缘或中国/美国公司"
            "而没有韩国市场传导证据的内容必须丢弃。"
        ),
    }.get(spec.market, "")
    if market_guardrail:
        market_guardrail += " 不要使用 example.com、示例链接或无法访问的占位 URL。"
    return (
        f"今天的日期是北京时间 {now_cn}。"
        f"请联网搜索并总结 {target_cn}（交易日 {target_iso}）{spec.scope}的主要资讯。"
        "重点包括：盘面主题或板块亮点、重大公司事件、政策监管、宏观或地缘新闻。"
        "不要重复指数或价格涨跌数据，行情数据已由系统抓取。"
        "不确定、传闻、没有明确来源或没有可访问 URL 的内容必须丢弃。"
        "不要做投资结论，不要预测市场方向。"
        f"{market_guardrail}"
        "如果查询结果显示该日期尚未结束或被视为未来时间，请自动回退到最近一个已经结束的交易日，并在摘要开头注明实际覆盖的日期与原因。"
        "输出需要使用中文、保持客观中性语气。"
        "请将完整内容放在单个 <news> 标签中，标签内优先输出 JSON："
        '{"items":[{"category":"policy|company|macro|sector","title":"新闻标题",'
        '"summary":"中文一句话事实摘要，不超过80字","source":"媒体或公告来源名称",'
        '"url":"https://...","published_at":"YYYY-MM-DD"}]}。'
        "每条必须有 source、url、published_at；无法满足则不要列入。"
        "除 <news>...</news> 外不要输出其它文本。"
        f"{extra}"
    )


def _build_ai_news_key_queues(
    settings_chain: list[_AiNewsSettings],
) -> dict[str, deque[tuple[str, str]]]:
    key_queues: dict[str, deque[tuple[str, str]]] = {}
    for settings in settings_chain:
        key_queue = deque(settings.keys)
        if len(key_queue) > 1:
            key_queue.rotate(-random.randint(0, len(key_queue) - 1))
        key_queues[settings.provider] = key_queue
    return key_queues
