"""Global lead-lag assets mapped to A-share concept signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LeadLagInstrument:
    symbol: str
    label: str
    market: str
    weight: float
    concepts: tuple[str, ...]


GLOBAL_LEAD_LAG_INSTRUMENTS: tuple[LeadLagInstrument, ...] = (
    LeadLagInstrument("NVDA", "NVIDIA", "US", 1.4, ("半导体设备", "算力概念", "AI芯片", "GPU概念")),
    LeadLagInstrument("AMD", "AMD", "US", 1.0, ("半导体设备", "AI芯片", "先进封装")),
    LeadLagInstrument("AVGO", "Broadcom", "US", 1.1, ("半导体设备", "AI芯片", "CPO概念")),
    LeadLagInstrument("TSLA", "Tesla", "US", 1.0, ("新能源车", "锂电池", "自动驾驶", "机器人")),
    LeadLagInstrument("AAPL", "Apple", "US", 1.0, ("消费电子", "果链", "面板", "AI手机")),
    LeadLagInstrument("MSFT", "Microsoft", "US", 1.0, ("AI应用", "云计算", "信创", "办公软件")),
    LeadLagInstrument("GOOGL", "Alphabet", "US", 1.0, ("AI应用", "云计算", "大模型")),
    LeadLagInstrument("AMZN", "Amazon", "US", 1.0, ("云计算", "跨境电商", "AI应用")),
    LeadLagInstrument("META", "Meta", "US", 1.0, ("元宇宙", "AI应用", "社交")),
    LeadLagInstrument(
        "8035.T", "Tokyo Electron", "JP", 1.2, ("半导体设备", "光刻胶", "材料国产替代")
    ),
    LeadLagInstrument("6857.T", "Advantest", "JP", 1.0, ("半导体设备", "测试设备", "先进封装")),
    LeadLagInstrument("6146.T", "Disco", "JP", 1.0, ("半导体设备", "先进封装", "晶圆切割")),
    LeadLagInstrument("6723.T", "Renesas", "JP", 0.8, ("汽车芯片", "MCU", "功率半导体")),
    LeadLagInstrument("6920.T", "Lasertec", "JP", 1.1, ("半导体设备", "光刻机", "EUV检测")),
    LeadLagInstrument(
        "005930.KS", "Samsung Electronics", "KR", 1.1, ("存储芯片", "HBM", "消费电子")
    ),
    LeadLagInstrument("000660.KS", "SK Hynix", "KR", 1.2, ("存储芯片", "HBM", "先进封装")),
    LeadLagInstrument(
        "042700.KS", "Hanmi Semiconductor", "KR", 1.0, ("HBM", "先进封装", "半导体设备")
    ),
)

BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "SMH", "^N225", "^KS11")

# Index label mapping for display
INDEX_LABELS: dict[str, str] = {
    "SPY": "标普500 ETF",
    "QQQ": "纳斯达克100 ETF",
    "SMH": "费城半导体 ETF",
    "^N225": "日经225",
    "^KS11": "韩国KOSPI",
}

GLOBAL_LEAD_LAG_SYMBOLS: tuple[str, ...] = tuple(
    instrument.symbol for instrument in GLOBAL_LEAD_LAG_INSTRUMENTS
)

US_TO_A_MAPPING: dict[str, list[str]] = {
    instrument.symbol: list(instrument.concepts)
    for instrument in GLOBAL_LEAD_LAG_INSTRUMENTS
    if instrument.market == "US"
}


def fetch_symbols() -> list[str]:
    return list(dict.fromkeys([*GLOBAL_LEAD_LAG_SYMBOLS, *BENCHMARK_SYMBOLS]))


def aggregate_concept_signals(
    quotes: dict[str, dict[str, Any]],
    mapping_table: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate external equity moves into weighted A-share concept signals."""
    if mapping_table is None:
        instruments = GLOBAL_LEAD_LAG_INSTRUMENTS
    else:
        instruments = tuple(
            LeadLagInstrument(
                symbol=symbol, label=symbol, market="custom", weight=1.0, concepts=tuple(concepts)
            )
            for symbol, concepts in mapping_table.items()
        )

    concept_scores: dict[str, dict[str, Any]] = {}
    for instrument in instruments:
        info = quotes.get(instrument.symbol, {})
        if "pct_chg" not in info:
            continue
        pct = float(info["pct_chg"])
        for concept in instrument.concepts:
            bucket = concept_scores.setdefault(
                concept,
                {"weighted_sum": 0.0, "weight": 0.0, "drivers": [], "markets": set()},
            )
            bucket["weighted_sum"] += pct * instrument.weight
            bucket["weight"] += instrument.weight
            bucket["drivers"].append(f"{instrument.symbol} {pct:+.1f}%")
            bucket["markets"].add(instrument.market)

    ranked: list[dict[str, Any]] = []
    for concept, data in concept_scores.items():
        total_weight = float(data["weight"])
        if total_weight <= 0:
            continue
        avg = float(data["weighted_sum"]) / total_weight
        signal = "bullish" if avg > 1 else "bearish" if avg < -1 else "neutral"
        ranked.append(
            {
                "concept": concept,
                "avg_pct_chg": round(avg, 2),
                "signal": signal,
                "drivers": data["drivers"],
                "markets": sorted(data["markets"]),
                "total_weight": round(total_weight, 2),
            }
        )
    ranked.sort(key=lambda item: item["avg_pct_chg"], reverse=True)
    return ranked
