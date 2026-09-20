"""Build deterministic market facts from normalized fetcher payloads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .models import MarketFact


def _now() -> datetime:
    return datetime.now(UTC)


def _fact(
    fact_id: str,
    metric: str,
    instrument: str | None,
    value: Any,
    previous: Any,
    change: Any,
    unit: str | None,
    source: str,
    as_of: datetime,
    quality: str = "ok",
) -> MarketFact:
    return MarketFact(
        id=fact_id,
        metric=metric,
        instrument=instrument,
        value=value,
        previous=previous,
        change=change,
        unit=unit,
        source=source,
        source_url=None,
        source_time=as_of,
        retrieved_at=_now(),
        quality=quality,
    )


def build_market_facts(raw_payloads: Mapping[str, Any], *, as_of: datetime) -> list[MarketFact]:
    facts: list[MarketFact] = []
    treasury = raw_payloads.get("treasury")
    if isinstance(treasury, Mapping):
        for tenor, row in treasury.items():
            if not isinstance(row, Mapping) or "change_bp" not in row:
                continue
            normalized = str(tenor).lower().replace("y", "y")
            facts.append(
                _fact(
                    f"treasury.{normalized}.change_bp",
                    "yield_change",
                    normalized,
                    row["change_bp"],
                    row.get("previous"),
                    row["change_bp"],
                    "basis_points",
                    "treasury",
                    as_of,
                )
            )
    quotes = raw_payloads.get("quotes")
    if isinstance(quotes, Mapping):
        for symbol, row in quotes.items():
            if not isinstance(row, Mapping) or "value" not in row:
                continue
            value = row["value"]
            previous = row.get("previous")
            symbol_text = str(symbol).upper()
            if symbol_text == "SPX":
                fact_id, metric, unit = "index.spx.change_percent", "index_return", "percent"
                source = "quotes"
            elif symbol_text == "WTI":
                fact_id, metric, unit = (
                    "cross_market.wti.change_percent",
                    "commodity_return",
                    "percent",
                )
                source = "quotes"
            else:
                fact_id, metric, unit = f"quote.{symbol_text.lower()}.value", "quote", None
                source = "quotes"
            facts.append(
                _fact(fact_id, metric, symbol_text, value, previous, value, unit, source, as_of)
            )
    for source_name, payload in raw_payloads.items():
        if isinstance(payload, Exception):
            facts.append(
                _fact(
                    f"source.{source_name}.status",
                    "source_status",
                    None,
                    "degraded",
                    None,
                    None,
                    None,
                    source_name,
                    as_of,
                    quality="degraded",
                )
            )
    return facts


def merge_fact_batches(batches: Iterable[Sequence[MarketFact]]) -> list[MarketFact]:
    merged: dict[str, MarketFact] = {}
    for batch in batches:
        for fact in batch:
            current = merged.get(fact.id)
            if current is None or (current.quality != "ok" and fact.quality == "ok"):
                merged[fact.id] = fact
    return [merged[key] for key in sorted(merged)]


def classify_curve_move(facts: Sequence[MarketFact]) -> str | None:
    by_id = {fact.id: fact for fact in facts}
    short = by_id.get("treasury.2y.change_bp")
    long = by_id.get("treasury.10y.change_bp")
    if (
        short is None
        or long is None
        or not isinstance(short.value, (int, float))
        or not isinstance(long.value, (int, float))
    ):
        return None
    short_up = short.value > 0
    long_up = long.value > 0
    if short_up and long_up:
        return "bear_flattening" if short.value > long.value else "bear_steepening"
    if not short_up and not long_up:
        return "bull_steepening" if short.value < long.value else "bull_flattening"
    return "bear_steepening" if short_up else "bull_steepening"
