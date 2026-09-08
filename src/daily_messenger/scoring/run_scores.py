#!/usr/bin/env python3
"""Derive scores and action recommendations from raw ETL output."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import yaml

from daily_messenger.common import run_meta
from daily_messenger.common.logging import log, setup_logger
from daily_messenger.scoring.adaptors import sentiment as sentiment_adaptor

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = PROJECT_ROOT / "out"
STATE_DIR = PROJECT_ROOT / "state"
CONFIG_PATH = PROJECT_ROOT / "config" / "weights.yml"
SENTIMENT_HISTORY_PATH = STATE_DIR / "sentiment_history.json"
SCORE_HISTORY_PATH = STATE_DIR / "score_history.json"

PUT_CALL_HISTORY_LIMIT = 252
AAII_HISTORY_LIMIT = 104


@dataclass
class ThemeScore:
    name: str
    label: str
    total: float
    breakdown: dict[str, float]
    degraded: bool = False
    breakdown_detail: dict[str, dict[str, object]] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    meta: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        detail_payload: dict[str, dict[str, object]] = {}
        for key, detail in self.breakdown_detail.items():
            if not isinstance(detail, dict):
                continue
            item = {**detail}
            value = item.get("value")
            if isinstance(value, (int, float)):
                item["value"] = round(float(value), 2)
            raw = item.get("raw")
            if isinstance(raw, (int, float)):
                item["raw"] = round(float(raw), 4)
            detail_payload[key] = item
        return {
            "name": self.name,
            "label": self.label,
            "total": round(self.total, 2),
            "breakdown": {k: round(v, 2) for k, v in self.breakdown.items()},
            "breakdown_detail": detail_payload,
            "weights": {k: float(v) for k, v in self.weights.items()},
            "meta": self.meta,
            "degraded": self.degraded,
        }


@dataclass(frozen=True)
class _ScoringInputs:
    config: dict[str, object]
    weights: Mapping[str, object]
    thresholds: dict[str, float]
    config_version: object
    config_changed_at: object
    raw_events: dict[str, object]
    etl_status: dict[str, object]
    market_payload: dict[str, object]
    theme_details: dict[str, object]
    btc_payload: dict[str, object]
    sentiment_node: dict[str, object]
    market_missing: bool
    btc_missing: bool
    btc_signal_ok: bool


def _current_trading_day() -> str:
    override = os.getenv("DM_OVERRIDE_DATE")
    if override:
        return override
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _load_config() -> dict[str, object]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"缺少配置文件: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ValueError("配置文件格式错误，期待字典结构")
    config.setdefault("version", 0)
    return config


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _scale(value: float, midpoint: float = 0.0, sensitivity: float = 15.0) -> float:
    score = 50 + (value - midpoint) * sensitivity
    return max(0.0, min(100.0, score))


def _inverse_ratio_score(value: float | None, baseline: float, sensitivity: float) -> float:
    if value is None or value <= 0:
        return 50.0
    ratio = baseline / value
    return _scale(ratio, midpoint=1.0, sensitivity=sensitivity)


def _market_cap_score(value: float | None, baseline_trillions: float) -> float:
    if value is None or value <= 0:
        return 50.0
    trillions = value / 1_000_000_000_000
    return _scale(trillions, midpoint=baseline_trillions, sensitivity=6.0)


def _coerce_float(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _coerce_float_map(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, raw in value.items():
        number = _coerce_float(raw)
        if number is not None:
            result[str(key)] = number
    return result


def _as_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _make_detail(
    value: float,
    *,
    fallback: bool = False,
    reason: str | None = None,
    source: str | None = None,
    raw: object | None = None,
) -> dict[str, object]:
    detail: dict[str, object] = {"value": value, "fallback": fallback}
    if reason:
        detail["reason"] = reason
    if source:
        detail["source"] = source
    if raw is not None:
        detail["raw"] = raw
    return detail


def _append_history(
    history: dict[str, list[float]], key: str, value: float | None, limit: int
) -> None:
    if value is None:
        return
    series = history.setdefault(key, [])
    series.append(value)
    if len(series) > limit:
        del series[:-limit]


def _score_ai(
    market: Mapping[str, object],
    weights: dict[str, float],
    degraded: bool,
    sentiment_score: float = 50.0,
    sentiment_fallback: bool = False,
) -> ThemeScore:
    sectors_raw = market.get("sectors", []) if market else []
    sectors = (
        [item for item in sectors_raw if isinstance(item, Mapping)]
        if isinstance(sectors_raw, list)
        else []
    )
    themes_raw = market.get("themes", {}) if market else {}
    theme_ai_raw = themes_raw.get("ai", {}) if isinstance(themes_raw, Mapping) else {}
    theme_ai = theme_ai_raw if isinstance(theme_ai_raw, Mapping) else {}
    weights = dict(weights or {})

    perf_source = "主题行情"
    ai_perf = theme_ai.get("performance")
    if ai_perf is None:
        fallback_sector = next(
            (s.get("performance") for s in sectors if s.get("name") == "AI"), None
        )
        if fallback_sector is not None:
            perf_source = "板块代理"
            ai_perf = fallback_sector
        else:
            perf_source = "默认 1.0"
            ai_perf = 1.0
    ai_perf_value = _coerce_float(ai_perf)
    if ai_perf_value is None:
        perf_source = "默认 1.0"
        ai_perf_value = 1.0
    index_change = theme_ai.get("change_pct")
    if index_change is None:
        indices_raw = market.get("indices", [])
        indices = (
            [item for item in indices_raw if isinstance(item, Mapping)]
            if isinstance(indices_raw, list)
            else []
        )
        index_change = next(
            (i.get("change_pct") for i in indices if i.get("symbol") == "NDX"),
            0.0,
        )
    avg_pe = _coerce_float(theme_ai.get("avg_pe"))
    avg_ps = _coerce_float(theme_ai.get("avg_ps"))

    breakdown = {
        "fundamental": _scale(ai_perf_value, midpoint=1.0, sensitivity=40),
        "valuation": _inverse_ratio_score(avg_pe, baseline=35.0, sensitivity=90.0),
        "sentiment": sentiment_score,
        "liquidity": _inverse_ratio_score(avg_ps, baseline=8.0, sensitivity=70.0),
        "event": 70.0,
    }
    breakdown_detail: dict[str, dict[str, object]] = {}
    breakdown_detail["fundamental"] = _make_detail(
        breakdown["fundamental"],
        fallback=perf_source == "默认 1.0",
        reason="缺少主题表现，使用默认估计" if perf_source == "默认 1.0" else None,
        source=perf_source,
        raw=ai_perf_value,
    )
    valuation_missing = avg_pe is None or (isinstance(avg_pe, (int, float)) and avg_pe <= 0)
    breakdown_detail["valuation"] = _make_detail(
        breakdown["valuation"],
        fallback=valuation_missing,
        reason="缺少平均 PE，使用中性值" if valuation_missing else None,
        raw=avg_pe,
    )
    liquidity_missing = avg_ps is None or (isinstance(avg_ps, (int, float)) and avg_ps <= 0)
    breakdown_detail["liquidity"] = _make_detail(
        breakdown["liquidity"],
        fallback=liquidity_missing,
        reason="缺少平均 PS，使用中性值" if liquidity_missing else None,
        raw=avg_ps,
    )
    breakdown_detail["sentiment"] = _make_detail(
        breakdown["sentiment"],
        fallback=sentiment_fallback,
        reason="情绪数据缺口，使用中性值" if sentiment_fallback else None,
    )
    breakdown_detail["event"] = _make_detail(breakdown["event"], fallback=False, source="配置")

    total = sum(weights.get(k, 0.0) * breakdown[k] for k in breakdown)
    return ThemeScore(
        name="ai",
        label="AI",
        total=total,
        breakdown=breakdown,
        degraded=degraded,
        breakdown_detail=breakdown_detail,
        weights=weights,
    )


def _score_btc(
    btc: Mapping[str, object],
    weights: dict[str, float],
    degraded: bool,
    sentiment_score: float = 50.0,
    sentiment_fallback: bool = False,
) -> ThemeScore:
    if not btc:
        degraded = True
        btc = {"etf_net_inflow_musd": 0.0, "funding_rate": 0.0, "futures_basis": 0.0}
    weights = dict(weights or {})

    basis_raw = _coerce_float(btc.get("futures_basis"))
    if basis_raw is None:
        basis_raw = 0.0
        basis_missing = True
    else:
        basis_missing = False
    inflow_raw = _coerce_float(btc.get("etf_net_inflow_musd"))
    if inflow_raw is None:
        inflow_raw = 0.0
        inflow_missing = True
    else:
        inflow_missing = False

    breakdown = {
        "fundamental": 50.0,
        "valuation": _scale(-abs(basis_raw), midpoint=-0.01, sensitivity=250),
        "sentiment": sentiment_score,
        "liquidity": _scale(inflow_raw, midpoint=0.0, sensitivity=1.5),
        "event": 65.0,
    }
    breakdown_detail: dict[str, dict[str, object]] = {
        "fundamental": _make_detail(50.0, fallback=False, source="配置"),
        "valuation": _make_detail(
            breakdown["valuation"],
            fallback=basis_missing,
            reason="缺少期货基差，使用中性值" if basis_missing else None,
            raw=basis_raw,
        ),
        "sentiment": _make_detail(
            breakdown["sentiment"],
            fallback=sentiment_fallback,
            reason="资金费率缺失，使用中性值" if sentiment_fallback else None,
            raw=_coerce_float(btc.get("funding_rate")),
        ),
        "liquidity": _make_detail(
            breakdown["liquidity"],
            fallback=inflow_missing,
            reason="ETF 净流入缺失，使用中性值" if inflow_missing else None,
            raw=inflow_raw,
        ),
        "event": _make_detail(65.0, fallback=False, source="配置"),
    }
    total = sum(weights.get(k, 0.0) * breakdown[k] for k in breakdown)
    return ThemeScore(
        name="btc",
        label="BTC",
        total=total,
        breakdown=breakdown,
        degraded=degraded,
        breakdown_detail=breakdown_detail,
        weights=weights,
    )


def _score_magnificent7(
    market: Mapping[str, object],
    weights: dict[str, float],
    degraded: bool,
    sentiment_score: float = 50.0,
    sentiment_fallback: bool = False,
) -> ThemeScore:
    themes = market.get("themes", {}) if market else {}
    theme_raw = themes.get("magnificent7", {}) if isinstance(themes, Mapping) else {}
    theme = cast(Mapping[str, object], theme_raw) if isinstance(theme_raw, Mapping) else {}
    weights = dict(weights or {})
    avg_pe = _coerce_float(theme.get("avg_pe"))
    avg_ps = _coerce_float(theme.get("avg_ps"))
    market_cap = _coerce_float(theme.get("market_cap"))

    breakdown = {
        "fundamental": _market_cap_score(market_cap, baseline_trillions=11.5),
        "valuation": _inverse_ratio_score(avg_pe, baseline=32.0, sensitivity=85.0),
        "sentiment": sentiment_score,
        "liquidity": _inverse_ratio_score(avg_ps, baseline=7.0, sensitivity=65.0),
        "event": 68.0,
    }
    breakdown_detail: dict[str, dict[str, object]] = {}
    fundamental_missing = market_cap is None or (
        isinstance(market_cap, (int, float)) and market_cap <= 0
    )
    breakdown_detail["fundamental"] = _make_detail(
        breakdown["fundamental"],
        fallback=fundamental_missing,
        reason="缺少总市值，使用中性值" if fundamental_missing else None,
        raw=market_cap,
    )
    valuation_missing = avg_pe is None or (isinstance(avg_pe, (int, float)) and avg_pe <= 0)
    breakdown_detail["valuation"] = _make_detail(
        breakdown["valuation"],
        fallback=valuation_missing,
        reason="缺少平均 PE，使用中性值" if valuation_missing else None,
        raw=avg_pe,
    )
    liquidity_missing = avg_ps is None or (isinstance(avg_ps, (int, float)) and avg_ps <= 0)
    breakdown_detail["liquidity"] = _make_detail(
        breakdown["liquidity"],
        fallback=liquidity_missing,
        reason="缺少平均 PS，使用中性值" if liquidity_missing else None,
        raw=avg_ps,
    )
    breakdown_detail["sentiment"] = _make_detail(
        breakdown["sentiment"],
        fallback=sentiment_fallback,
        reason="情绪数据缺口，使用中性值" if sentiment_fallback else None,
    )
    breakdown_detail["event"] = _make_detail(breakdown["event"], fallback=False, source="配置")
    total = sum(weights.get(k, 0.0) * breakdown[k] for k in breakdown)
    return ThemeScore(
        name="magnificent7",
        label="Magnificent 7",
        total=total,
        breakdown=breakdown,
        degraded=degraded,
        breakdown_detail=breakdown_detail,
        weights=weights,
    )


def _build_actions(themes: list[ThemeScore], thresholds: dict[str, float]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for theme in themes:
        if theme.degraded:
            actions.append(
                {"name": theme.label, "action": "保持观察", "reason": "数据降级，保持中性"}
            )
            continue
        if theme.total >= thresholds.get("action_add", 75):
            actions.append(
                {
                    "name": theme.label,
                    "action": "关注增强",
                    "reason": f"总分 {theme.total:.0f} 高于关注增强阈值",
                }
            )
        elif theme.total <= thresholds.get("action_trim", 45):
            actions.append(
                {
                    "name": theme.label,
                    "action": "关注降温",
                    "reason": f"总分 {theme.total:.0f} 低于关注降温阈值",
                }
            )
        else:
            actions.append(
                {
                    "name": theme.label,
                    "action": "保持观察",
                    "reason": f"总分 {theme.total:.0f} 处于中性区间",
                }
            )
    return actions


def _save_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _source_status_map(etl_status: Mapping[str, object]) -> dict[str, bool]:
    sources_raw = etl_status.get("sources", [])
    source_status: dict[str, bool] = {}
    if not isinstance(sources_raw, list):
        return source_status
    for entry in sources_raw:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str):
                source_status[name] = bool(entry.get("ok"))
        elif isinstance(entry, str):
            source_status[entry] = True
    return source_status


def _load_scoring_inputs(logger: logging.Logger) -> _ScoringInputs:
    config = _load_config()
    weights_raw = config.get("weights", {})
    weights = cast(Mapping[str, object], weights_raw) if isinstance(weights_raw, Mapping) else {}
    thresholds = _coerce_float_map(config.get("thresholds", {}))

    raw_market = _load_json(OUT_DIR / "raw_market.json")
    raw_events = _load_json(OUT_DIR / "raw_events.json")
    etl_status = _load_json(OUT_DIR / "etl_status.json")
    source_status = _source_status_map(etl_status)

    raw_market_payload = _as_dict(raw_market)
    market_payload = _as_dict(raw_market_payload.get("market", {}))
    theme_details = _as_dict(market_payload.get("themes", {}))
    btc_payload = _as_dict(raw_market_payload.get("btc", {}))
    sentiment_node = _as_dict(raw_market_payload.get("sentiment", {}))

    market_missing = not market_payload
    if market_missing:
        log(logger, logging.WARNING, "scoring_missing_market_data")
    if not raw_events:
        log(logger, logging.WARNING, "scoring_missing_events")

    btc_signals = ("coinbase_spot", "okx_funding", "okx_basis")
    btc_signal_ok = all(source_status.get(name, True) for name in btc_signals)
    return _ScoringInputs(
        config=config,
        weights=weights,
        thresholds=thresholds,
        config_version=config.get("version"),
        config_changed_at=config.get("changed_at"),
        raw_events=raw_events,
        etl_status=etl_status,
        market_payload=market_payload,
        theme_details=theme_details,
        btc_payload=btc_payload,
        sentiment_node=sentiment_node,
        market_missing=market_missing,
        btc_missing=not btc_payload,
        btc_signal_ok=btc_signal_ok,
    )


def _load_sentiment_history() -> dict[str, list[float]]:
    existing_history = _load_json(SENTIMENT_HISTORY_PATH)
    history: dict[str, list[float]] = {}
    for key, limit in (
        ("put_call_equity", PUT_CALL_HISTORY_LIMIT),
        ("aaii_bull_bear_spread", AAII_HISTORY_LIMIT),
    ):
        raw_values = existing_history.get(key)
        series: list[float] = []
        if isinstance(raw_values, list):
            for value in raw_values:
                number = _coerce_float(value)
                if number is not None:
                    series.append(number)
        history[key] = series[-limit:]
    return history


def _update_sentiment_history(
    history: dict[str, list[float]],
    sentiment_node: Mapping[str, object],
) -> None:
    put_call = sentiment_node.get("put_call")
    if isinstance(put_call, dict):
        equity_value = _coerce_float(put_call.get("equity"))
        _append_history(history, "put_call_equity", equity_value, PUT_CALL_HISTORY_LIMIT)

    aaii = sentiment_node.get("aaii")
    if isinstance(aaii, dict):
        spread_value = _coerce_float(aaii.get("bull_bear_spread"))
        _append_history(history, "aaii_bull_bear_spread", spread_value, AAII_HISTORY_LIMIT)


def _resolve_sentiment(
    sentiment_node: dict[str, object],
) -> tuple[dict[str, list[float]], sentiment_adaptor.SentimentResult | None]:
    history = _load_sentiment_history()
    _update_sentiment_history(history, sentiment_node)
    result = sentiment_adaptor.aggregate(sentiment_node, history) if sentiment_node else None
    return history, result


def _score_themes(
    inputs: _ScoringInputs,
    sentiment_result: sentiment_adaptor.SentimentResult | None,
) -> list[ThemeScore]:
    sentiment_available = sentiment_result is not None
    sentiment_score_value = sentiment_result.score if sentiment_result else 50.0
    default_weights = inputs.weights.get("default", {})
    theme_ai_weights = _coerce_float_map(inputs.weights.get("theme_ai") or default_weights)
    theme_btc_weights = _coerce_float_map(inputs.weights.get("theme_btc") or default_weights)
    theme_m7_weights = _coerce_float_map(inputs.weights.get("theme_m7") or default_weights)

    theme_ai = _score_ai(
        inputs.market_payload,
        theme_ai_weights,
        inputs.market_missing,
        sentiment_score=sentiment_score_value,
        sentiment_fallback=not sentiment_available,
    )

    funding_rate_raw = _coerce_float(inputs.btc_payload.get("funding_rate", 0.0))
    funding_rate_for_score = funding_rate_raw if funding_rate_raw is not None else 0.0
    theme_btc = _score_btc(
        inputs.btc_payload,
        theme_btc_weights,
        inputs.btc_missing or not inputs.btc_signal_ok,
        sentiment_score=_scale(funding_rate_for_score, midpoint=0.005, sensitivity=600),
        sentiment_fallback=funding_rate_raw is None,
    )

    theme_m7 = _score_magnificent7(
        inputs.market_payload,
        theme_m7_weights,
        inputs.market_missing,
        sentiment_score=sentiment_score_value,
        sentiment_fallback=not sentiment_available,
    )
    return [theme_ai, theme_m7, theme_btc]


def _previous_theme_total(entries: list[object], trading_day: str) -> float | None:
    for entry in reversed(entries):
        if isinstance(entry, dict) and entry.get("date") != trading_day:
            return _coerce_float(entry.get("total"))
    return None


def _theme_history_meta(
    theme: ThemeScore,
    thresholds: dict[str, float],
    prev_total: float | None,
) -> dict[str, object]:
    delta = theme.total - prev_total if prev_total is not None else None
    meta: dict[str, object] = {
        "previous_total": round(prev_total, 2) if prev_total is not None else None,
        "delta": round(delta, 2) if delta is not None else None,
        "weights": {key: float(value) for key, value in theme.weights.items()},
    }
    add_threshold = thresholds.get("action_add")
    if isinstance(add_threshold, (int, float)):
        meta["distance_to_add"] = round(add_threshold - theme.total, 2)
    trim_threshold = thresholds.get("action_trim")
    if isinstance(trim_threshold, (int, float)):
        meta["distance_to_trim"] = round(theme.total - trim_threshold, 2)
    return meta


def _updated_theme_entries(
    entries: list[object],
    trading_day: str,
    total: float,
) -> list[dict[str, object]]:
    updated_entries = [
        cast(dict[str, object], entry)
        for entry in entries
        if isinstance(entry, dict) and entry.get("date") != trading_day
    ]
    updated_entries.append({"date": trading_day, "total": round(total, 2)})
    return updated_entries[-30:]


def _update_theme_history(
    themes: list[ThemeScore],
    thresholds: dict[str, float],
    trading_day: str,
) -> dict[str, object]:
    history_payload = _load_json(SCORE_HISTORY_PATH)
    themes_history = _as_dict(history_payload.get("themes"))
    for theme in themes:
        entries_raw = themes_history.get(theme.name, [])
        entries = cast(list[object], entries_raw) if isinstance(entries_raw, list) else []
        prev_total = _previous_theme_total(entries, trading_day)
        theme.meta = _theme_history_meta(theme, thresholds, prev_total)
        themes_history[theme.name] = _updated_theme_entries(entries, trading_day, theme.total)
    return themes_history


def _build_scores_payload(
    trading_day: str,
    themes: list[ThemeScore],
    global_degraded: bool,
    inputs: _ScoringInputs,
    sentiment_result: sentiment_adaptor.SentimentResult | None,
) -> dict[str, object]:
    scores_payload: dict[str, object] = {
        "date": trading_day,
        "themes": [theme.to_dict() for theme in themes],
        "events": inputs.raw_events.get("events", []),
        "degraded": global_degraded,
        "thresholds": inputs.thresholds,
        "etl_status": inputs.etl_status,
    }
    ai_updates = inputs.raw_events.get("ai_updates", [])
    if inputs.theme_details:
        scores_payload["theme_details"] = inputs.theme_details
    if isinstance(ai_updates, list) and ai_updates:
        scores_payload["ai_updates"] = ai_updates
    if inputs.config_version is not None:
        scores_payload["config_version"] = inputs.config_version
    if inputs.config_changed_at:
        scores_payload["config_changed_at"] = inputs.config_changed_at
    if sentiment_result:
        scores_payload["sentiment"] = sentiment_result.to_dict()
    return scores_payload


def _write_scoring_outputs(
    trading_day: str,
    history: dict[str, list[float]],
    scores_payload: Mapping[str, object],
    themes_history: dict[str, object],
    actions: list[dict[str, str]],
    state_path: Path,
) -> None:
    SENTIMENT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SENTIMENT_HISTORY_PATH.open("w", encoding="utf-8") as f_history:
        json.dump(history, f_history, ensure_ascii=False, indent=2)
    _save_json(OUT_DIR / "scores.json", scores_payload)
    _save_json(SCORE_HISTORY_PATH, {"themes": themes_history})
    _save_json(OUT_DIR / "actions.json", {"date": trading_day, "items": actions})

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path.write_text(trading_day, encoding="utf-8")


def _log_theme_scores(logger: logging.Logger, themes: list[ThemeScore]) -> None:
    for theme in themes:
        log(
            logger,
            logging.INFO,
            "theme_score",
            theme=theme.name,
            label=theme.label,
            total=round(theme.total, 2),
            degraded=theme.degraded,
        )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute theme scores")
    parser.add_argument("--force", action="store_true", help="忽略幂等标记，强制重新计算")
    args = parser.parse_args(argv)

    started_at = datetime.now(UTC)
    trading_day = _current_trading_day()
    logger = setup_logger("scoring", trading_day=trading_day)
    log(logger, logging.INFO, "scoring_start", force=args.force)
    run_meta.record_step(OUT_DIR, "scoring", "started", trading_day=trading_day, force=args.force)

    state_path = STATE_DIR / f"done_{trading_day}"

    if state_path.exists() and not args.force:
        log(logger, logging.INFO, "scoring_skip_cached", state_path=str(state_path))
        run_meta.record_step(OUT_DIR, "scoring", "cached", trading_day=trading_day)
        return 0

    inputs = _load_scoring_inputs(logger)
    history, sentiment_result = _resolve_sentiment(inputs.sentiment_node)
    themes = _score_themes(inputs, sentiment_result)
    global_degraded = any(theme.degraded for theme in themes)

    if global_degraded and os.getenv("STRICT"):
        log(logger, logging.ERROR, "scoring_strict_abort", strict=True)
        run_meta.record_step(
            OUT_DIR,
            "scoring",
            "failed",
            trading_day=trading_day,
            degraded=True,
            strict=True,
        )
        return 2

    actions = _build_actions(themes, inputs.thresholds)
    themes_history = _update_theme_history(themes, inputs.thresholds, trading_day)
    scores_payload = _build_scores_payload(
        trading_day,
        themes,
        global_degraded,
        inputs,
        sentiment_result,
    )
    _write_scoring_outputs(
        trading_day,
        history,
        scores_payload,
        themes_history,
        actions,
        state_path,
    )

    _log_theme_scores(logger, themes)
    duration = (datetime.now(UTC) - started_at).total_seconds()
    log(
        logger,
        logging.INFO,
        "scoring_complete",
        degraded=global_degraded,
        themes=len(themes),
        duration_seconds=round(duration, 2),
        config_version=inputs.config_version,
    )
    run_meta.record_step(
        OUT_DIR,
        "scoring",
        "completed",
        trading_day=trading_day,
        degraded=global_degraded,
        duration_seconds=round(duration, 2),
        config_version=inputs.config_version,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
