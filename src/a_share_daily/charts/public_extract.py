"""Small, source-dated point sets from the inputs of the six Feishu charts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import cast

import pandas as pd

from .sentiment import _sentiment_stats
from .topic import format_topic_label
from .us_overnight import LABELS, SYMBOLS
from .weekly_chart import _daily_stats, _weekly_period


def _iso(value: object) -> str:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    parsed = date.fromisoformat(text)
    return parsed.isoformat()


def _point(
    label: str, value: object, unit: str, day: str, source: Mapping[str, str]
) -> dict[str, object]:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"non-numeric chart point: {label}")
    return {
        "label": label,
        "value": float(value),
        "unit": unit,
        "observation_date": _iso(day),
        "source_label": source["source_label"],
        "source_url": source["source_url"],
    }


def _frame(value: object, key: str) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise ValueError(f"{key} must be a DataFrame")
    return value


def _mapping(value: object, key: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return cast("Mapping[str, object]", value)


def _week_frames(value: object) -> dict[str, pd.DataFrame]:
    raw = _mapping(value, "week_daily")
    return {str(day): _frame(frame, "week_daily row") for day, frame in raw.items()}


def _source(key: str, inputs: Mapping[str, object]) -> dict[str, str]:
    return {
        "date": _iso(inputs[f"{key}_observation_date"]),
        "source_label": str(inputs[f"{key}_source_label"]),
        "source_url": str(inputs[f"{key}_source_url"]),
    }


def _sentiment(inputs: Mapping[str, object], source: Mapping[str, str]) -> list[dict[str, object]]:
    daily = _frame(inputs["daily"], "daily")
    up, down, flat, average, total = _sentiment_stats(daily)
    day = source["date"]
    rows = [
        ("上涨家数", up, "家"),
        ("下跌家数", down, "家"),
        ("平盘家数", flat, "家"),
        ("个股总数", total, "家"),
        ("平均涨跌", average, "%"),
        ("涨停家数", inputs["limit_up_count"], "家"),
    ]
    return [_point(label, value, unit, day, source) for label, value, unit in rows]


def _dashboard(inputs: Mapping[str, object], source: Mapping[str, str]) -> list[dict[str, object]]:
    daily = _frame(inputs["daily"], "daily")
    up, down, flat, average, _ = _sentiment_stats(daily)
    day = source["date"]
    rows = [
        _point("上涨家数", up, "家", day, source),
        _point("下跌家数", down, "家", day, source),
        _point("平盘家数", flat, "家", day, source),
        _point("平均涨跌", average, "%", day, source),
        _point("涨停家数", inputs["limit_up_count"], "家", day, source),
        _point("最高连板", inputs["max_board"], "板", day, source),
    ]
    for row in _frame(inputs["turnover"], "turnover").to_dict("records"):
        observed = _iso(row["date"])
        rows.append(_point(f"成交额 {observed}", row["amount"], "亿", observed, source))
    for row in _frame(inputs["margin"], "margin").to_dict("records"):
        observed = _iso(row["date"])
        rows.append(_point(f"融资余额 {observed}", row["rzye"], "亿", observed, source))
    return rows


def _moneyflow(inputs: Mapping[str, object], source: Mapping[str, str]) -> list[dict[str, object]]:
    data = _frame(inputs["moneyflow"], "moneyflow")
    selected = data[data["net_amount"].abs() > 1_000]
    ranked = pd.concat(
        [selected.nlargest(8, "net_amount"), selected.nsmallest(5, "net_amount")]
    ).drop_duplicates(subset=["ts_code"])
    rows = []
    for _, row in ranked.iterrows():
        label = f"{row['name']} {str(row['ts_code'])[:6]}"
        rows.append(_point(label, row["net_amount"] / 1e4, "亿元", source["date"], source))
    return rows


def _topic(inputs: Mapping[str, object], source: Mapping[str, str]) -> list[dict[str, object]]:
    summary = _mapping(inputs["topic"], "topic")
    observed = _iso(summary["source_date"])
    raw_topics = summary["topics"]
    if not isinstance(raw_topics, list):
        raise ValueError("topic topics must be a list")
    topics = sorted(
        (_mapping(item, "topic row") for item in raw_topics),
        key=lambda item: float(str(item["weight"])),
        reverse=True,
    )[:10]
    return [
        _point(
            format_topic_label(item.get("topic")),
            float(str(item["weight"])) * 100
            if float(str(item["weight"])) <= 1
            else float(str(item["weight"])),
            "%",
            observed,
            source,
        )
        for item in topics
    ]


def _weekly(
    inputs: Mapping[str, object], source: Mapping[str, str], target: str
) -> list[dict[str, object]]:
    by_date = _week_frames(inputs["week_daily"])
    _, _, dates = _weekly_period(by_date, target.replace("-", ""))
    if len(dates) < 2:
        return []
    stats = _daily_stats(by_date, dates)
    rows = []
    for _, row in stats.iterrows():
        observed = _iso(row["date"])
        for label, field, unit in (
            ("上涨家数", "up", "家"),
            ("下跌家数", "down", "家"),
            ("平盘家数", "flat", "家"),
            ("成交额", "amount", "亿"),
        ):
            rows.append(_point(f"{label} {observed}", row[field], unit, observed, source))
    return rows


def _overnight(inputs: Mapping[str, object], source: Mapping[str, str]) -> list[dict[str, object]]:
    stocks = _mapping(inputs["us_stocks"], "us_stocks")
    rows = []
    for symbol, label in zip(SYMBOLS, LABELS, strict=True):
        raw_quote = stocks.get(symbol)
        if not isinstance(raw_quote, Mapping):
            continue
        quote = cast("Mapping[str, object]", raw_quote)
        if "pct_chg" not in quote or not quote.get("as_of_date"):
            continue
        rows.append(_point(label, quote["pct_chg"], "%", _iso(quote["as_of_date"]), source))
    return rows


_EXTRACTORS = {
    "dashboard": _dashboard,
    "moneyflow": _moneyflow,
    "topic": _topic,
    "sentiment": _sentiment,
    "us_overnight": _overnight,
}


def extract_chart_points(
    key: str, inputs: Mapping[str, object], target_date: str
) -> list[dict[str, object]]:
    """Extract only display points, preserving each component's source date."""
    source = _source(key, inputs)
    if key == "weekly_chart":
        return _weekly(inputs, source, target_date)
    try:
        extractor = _EXTRACTORS[key]
    except KeyError as exc:
        raise ValueError(f"unknown chart key: {key}") from exc
    return extractor(inputs, source)
