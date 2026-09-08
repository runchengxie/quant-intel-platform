"""Post-market daily review.

Facts builder and renderer for the A-share evening review. Provides index-level
tracking (上证/深证/创业板/科创50/沪深300), industry-level stats (via ths_member),
intraday structure (OHLC-based), VWAP analysis, exact exchange limit-price
classification with an explicit fallback, and structured text + JSON output.
"""

from .. import data as D
from .loaders import (
    DEFAULT_EVENING_ARCHIVE_DIR,
    build_review_payload,
    load_hot_sectors,
    load_index_overview,
    load_industry_stats,
    load_limit_analysis,
    load_margin,
    load_market_overview,
    load_moneyflow,
    load_previous_market_temperature,
    load_top_amount_stocks,
    load_turnover_history,
)
from .renderers import build_json, build_report, run

__all__ = [
    "D",
    "DEFAULT_EVENING_ARCHIVE_DIR",
    "build_review_payload",
    "load_index_overview",
    "load_market_overview",
    "load_limit_analysis",
    "load_moneyflow",
    "load_margin",
    "load_hot_sectors",
    "load_industry_stats",
    "load_top_amount_stocks",
    "load_turnover_history",
    "load_previous_market_temperature",
    "build_report",
    "build_json",
    "run",
]
