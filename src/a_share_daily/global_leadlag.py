"""Global lead-lag assets mapped to A-share concept signals."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import pandas as pd


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

BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "SMH", "^HSI", "^N225", "^KS11")

# Index label mapping for display
INDEX_LABELS: dict[str, str] = {
    "SPY": "标普500 ETF",
    "QQQ": "纳斯达克100 ETF",
    "SMH": "VanEck 半导体 ETF",
    "^HSI": "恒生指数",
    "^N225": "日经225",
    "^KS11": "韩国KOSPI",
}

MAPPING_VERSION = "overseas_concepts.v1"

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
    *,
    decision_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Describe weighted overseas moves; never infer A-share prediction confidence.

    With a cutoff, require the latest completed exchange session and provenance.
    Session close is a source time, not proof of historical retrieval availability.
    The legacy signal key remains neutral for compatibility with old consumers.
    """
    if decision_at is not None and decision_at.tzinfo is None:
        raise ValueError("decision_at must have a timezone")
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
        observation = _observation(instrument, info, decision_at)
        if observation is None:
            continue
        pct = observation["pct_chg"]
        for concept in instrument.concepts:
            bucket = concept_scores.setdefault(
                concept,
                {
                    "weighted_sum": 0.0,
                    "weight": 0.0,
                    "drivers": [],
                    "markets": set(),
                    "observations": [],
                },
            )
            bucket["weighted_sum"] += pct * instrument.weight
            bucket["weight"] += instrument.weight
            bucket["drivers"].append(f"{instrument.symbol} {pct:+.1f}%")
            bucket["markets"].add(instrument.market)
            bucket["observations"].append(observation)

    ranked: list[dict[str, Any]] = []
    for concept, data in concept_scores.items():
        total_weight = float(data["weight"])
        if total_weight <= 0:
            continue
        avg = float(data["weighted_sum"]) / total_weight
        movement = "up" if avg > 1 else "down" if avg < -1 else "mixed"
        ranked.append(
            {
                "concept": concept,
                "avg_pct_chg": round(avg, 2),
                "signal": "neutral",
                "movement": movement,
                "mapping_version": MAPPING_VERSION
                if mapping_table is None
                else "custom_unversioned",
                "evidence_status": (
                    "descriptive_session_checked" if decision_at else "descriptive_unverified"
                ),
                "observations": data["observations"],
                "drivers": data["drivers"],
                "markets": sorted(data["markets"]),
                "total_weight": round(total_weight, 2),
            }
        )
    ranked.sort(key=lambda item: item["avg_pct_chg"], reverse=True)
    return ranked


def _observation(
    instrument: LeadLagInstrument, info: dict[str, Any], decision_at: datetime | None
) -> dict[str, Any] | None:
    if not isinstance(info, dict):
        return None
    value = info.get("pct_chg")
    if value is None or isinstance(value, bool):
        return None
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(pct) or info.get("error"):
        return None
    observation = {
        "evidence_id": f"quote:{instrument.symbol}:{info.get('as_of_date', 'undated')}",
        "symbol": instrument.symbol,
        "pct_chg": pct,
        "as_of_date": info.get("as_of_date"),
        "source_url": info.get("source_url"),
        "source_time_utc": None,
    }
    if decision_at is not None:
        try:
            _qualify_observation(instrument, info, decision_at, observation)
        except (KeyError, TypeError, ValueError):
            return None
    return observation


def _qualify_observation(instrument, info, decision_at, observation) -> None:
    import exchange_calendars as xcals

    calendar_name = {"US": "XNYS", "JP": "XTKS", "KR": "XKRX"}[instrument.market]
    calendar = xcals.get_calendar(calendar_name)
    cutoff = pd.Timestamp(decision_at).tz_convert("UTC")
    session = calendar.date_to_session(decision_at.astimezone(UTC).date(), direction="previous")
    while calendar.session_close(session) > cutoff:
        session = calendar.previous_session(session)
    if info.get("as_of_date") != session.date().isoformat():
        raise ValueError("not_latest_completed_session")
    url = urlparse(str(info.get("source_url", "")))
    if url.scheme not in {"http", "https"} or not url.netloc:
        raise ValueError("missing_source_url")
    for field in ("observed_at_utc", "retrieved_at_utc"):
        if field in info:
            observed = pd.Timestamp(info[field])
            if pd.isna(observed) or observed.tzinfo is None or observed > cutoff:
                raise ValueError("invalid_observation_time")
    observation["source_time_utc"] = calendar.session_close(session).isoformat()


def legacy_observations(raw: Any) -> list[dict[str, Any]]:
    """Retain displayable legacy averages without trusting their claimed provenance."""
    result = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("concept"), str):
            continue
        value = item.get("avg_pct_chg")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            continue
        result.append(
            {
                "concept": item["concept"],
                "avg_pct_chg": value,
                "signal": "neutral",
                "movement": "mixed",
                "mapping_version": "legacy_unversioned",
                "evidence_status": "descriptive_unverified",
                "observations": [],
                "drivers": [x for x in item.get("drivers", []) if isinstance(x, str)]
                if isinstance(item.get("drivers"), list)
                else [],
                "markets": [x for x in item.get("markets", []) if isinstance(x, str)]
                if isinstance(item.get("markets"), list)
                else [],
            }
        )
    return result
