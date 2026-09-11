"""Render a descriptive market-temperature panel.

The chart deliberately keeps risk appetite (``heat``) and market stress
(``fragility``) separate.  It is an observation aid, not a position-sizing
model, and missing values are rendered as ``N/A`` instead of being coerced to
zero.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import matplotlib.pyplot as plt

from .theme import (
    BG,
    DOWN,
    FG,
    LINE,
    MUTED,
    UP,
    YELLOW,
    apply_editorial_background,
    cjk,
    cjk_display,
)

_MUTED = MUTED
_MISSING = object()

_DIMENSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "流动性",
        ("流动性", "量能", "量能得分", "liquidity", "liquidity_score", "volume_score"),
    ),
    ("广度", ("广度", "广度得分", "breadth", "breadth_score")),
    (
        "赚钱效应",
        ("赚钱效应", "赚钱", "赚钱得分", "profit", "profit_effect", "profit_score"),
    ),
    (
        "亏钱风险",
        (
            "亏钱风险",
            "亏钱压力",
            "亏钱效应",
            "loss",
            "loss_effect",
            "loss_pressure",
            "loss_risk",
        ),
    ),
    (
        "趋势确认",
        (
            "趋势确认",
            "trend",
            "trend_score",
            "trend_confirmation",
            "structure_confirmation",
        ),
    ),
    (
        "轮动质量",
        (
            "轮动质量",
            "轮动结构",
            "轮动",
            "rotation",
            "rotation_quality",
            "sector_rotation",
        ),
    ),
)


def generate_market_temperature(
    temperature: Mapping[str, Any],
    trade_date: str,
    out_path: str = "out/a_share_daily/daily_sentiment_chart.png",
) -> str:
    """Generate an editorial light-theme market-temperature chart and return its path.

    The preferred payload uses ``status_label``, ``heat_score``,
    ``fragility_score``, ``dimensions`` and ``core_tensions``. Common Chinese and English aliases
    are accepted so the renderer remains independent from a particular scoring
    producer.
    """
    status = _status_label(temperature)
    heat = _score_from(
        temperature,
        ("heat", "heat_score", "temperature_score", "热度", "热度分"),
    )
    fragility = _score_from(
        temperature,
        (
            "fragility",
            "fragility_score",
            "vulnerability",
            "vulnerability_score",
            "risk_score",
            "脆弱度",
            "脆弱度分",
        ),
    )
    dimensions = _dimension_values(temperature)
    contradictions = _contradictions(temperature)

    fig = plt.figure(figsize=(10, 8))
    apply_editorial_background(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    _draw_header(ax, trade_date, status, heat, fragility)
    _draw_dimension_section(ax, dimensions)
    _draw_tension_section(ax, contradictions)

    ax.text(
        0.5,
        0.045,
        "观察分 / 未回测 / 不直接映射仓位",
        fontsize=10,
        color=_MUTED,
        fontproperties=cjk,
        ha="center",
        va="center",
    )

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=BG, edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


def _draw_header(
    ax: Any,
    trade_date: str,
    status: str,
    heat: float | None,
    fragility: float | None,
) -> None:
    ax.text(
        0.05,
        0.955,
        f"市场温度计 · {_display_date(trade_date)}",
        fontsize=20,
        color=FG,
        fontproperties=cjk_display,
        va="top",
    )
    ax.text(
        0.95,
        0.948,
        "热度与风险分开观察",
        fontsize=10.5,
        color=_MUTED,
        fontproperties=cjk,
        ha="right",
        va="top",
    )

    ax.text(
        0.05,
        0.825,
        "当前状态",
        fontsize=10,
        color=_MUTED,
        fontproperties=cjk,
        va="center",
    )
    ax.text(
        0.20,
        0.825,
        status,
        fontsize=17,
        color=_status_color(heat, fragility),
        fontproperties=cjk,
        fontweight="bold",
        va="center",
    )

    ax.plot([0.50, 0.50], [0.70, 0.80], color=LINE, linewidth=0.8, transform=ax.transAxes)
    for x, title, score, accent in (
        (0.05, "市场热度", heat, _score_color(heat)),
        (0.57, "市场脆弱度", fragility, _fragility_color(fragility)),
    ):
        ax.text(x, 0.755, title, fontsize=10, color=_MUTED, fontproperties=cjk, va="center")
        ax.text(
            x,
            0.705,
            _format_score(score),
            fontsize=24,
            color=accent if score is not None else _MUTED,
            fontproperties=cjk_display,
            va="center",
        )


def _draw_dimension_section(ax: Any, dimensions: Sequence[float | None]) -> None:
    ax.text(
        0.05,
        0.655,
        "六维观察",
        fontsize=12.5,
        color=FG,
        fontproperties=cjk,
        fontweight="bold",
        va="center",
    )
    ax.text(
        0.95,
        0.655,
        "点位越右，分数越高",
        fontsize=9,
        color=_MUTED,
        fontproperties=cjk,
        ha="right",
        va="center",
    )
    for x, label in ((0.23, "0"), (0.54, "50"), (0.85, "100")):
        ax.text(x, 0.625, label, fontsize=8, color=_MUTED, fontproperties=cjk, ha="center")

    for index, ((label, _), score) in enumerate(zip(_DIMENSIONS, dimensions, strict=True)):
        _draw_dimension_dot(
            ax,
            label=label,
            score=score,
            y=0.605 - index * 0.055,
        )


def _draw_tension_section(ax: Any, contradictions: Sequence[str]) -> None:
    ax.text(
        0.05,
        0.270,
        "核心矛盾",
        fontsize=12.5,
        color=FG,
        fontproperties=cjk,
        fontweight="bold",
        va="center",
    )
    if contradictions:
        for index, contradiction in enumerate(contradictions):
            ax.text(
                0.08,
                0.215 - index * 0.060,
                f"{index + 1:02d}  {_ellipsize(contradiction, 58)}",
                fontsize=10.5,
                color=FG,
                fontproperties=cjk,
                va="center",
            )
    else:
        ax.text(
            0.08,
            0.195,
            "暂无可用核心矛盾",
            fontsize=10.5,
            color=_MUTED,
            fontproperties=cjk,
            va="center",
        )


def _draw_dimension_dot(
    ax: Any,
    *,
    label: str,
    score: float | None,
    y: float,
) -> None:
    ax.text(
        0.06,
        y,
        label,
        fontsize=10.5,
        color=FG,
        fontproperties=cjk,
        va="center",
    )
    ax.plot([0.23, 0.85], [y, y], color=LINE, linewidth=0.8, transform=ax.transAxes)
    if score is not None:
        color = _dimension_color(label, score)
        ax.plot(
            [0.23 + 0.62 * score / 100],
            [y],
            marker="o",
            markersize=7,
            color=color,
            transform=ax.transAxes,
        )
    ax.text(
        0.94,
        y,
        _format_score(score),
        fontsize=10.5,
        color=_dimension_color(label, score) if score is not None else _MUTED,
        fontproperties=cjk,
        fontweight="bold" if score is not None else "normal",
        ha="right",
        va="center",
    )
    if label == "亏钱风险" and score is not None and score >= 55:
        ax.text(0.76, y, "风险偏高", fontsize=8.5, color=UP, fontproperties=cjk, va="center")


def _dimension_color(label: str, score: float) -> str:
    if label == "亏钱风险" and score >= 55:
        return UP
    if score < 35:
        return DOWN
    if score >= 65:
        return UP
    return YELLOW


def _dimension_values(temperature: Mapping[str, Any]) -> list[float | None]:
    raw = _first(temperature, ("dimensions", "six_dimensions", "六维", "六维评分"))
    dimension_map = _as_dimension_mapping(raw)
    values: list[float | None] = []
    for _, aliases in _DIMENSIONS:
        value = _first(dimension_map, aliases)
        if value is _MISSING:
            value = _first(temperature, aliases)
        values.append(_as_score(value))
    return values


def _as_dimension_mapping(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        mapped: dict[str, Any] = {}
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            name = _first(item, ("name", "label", "dimension", "维度"))
            value = _first(item, ("score", "value", "得分"))
            if name is not _MISSING and value is not _MISSING:
                mapped[str(name)] = value
        return mapped
    return {}


def _score_from(source: Mapping[str, Any], aliases: tuple[str, ...]) -> float | None:
    return _as_score(_first(source, aliases))


def _as_score(value: Any) -> float | None:
    if isinstance(value, Mapping):
        value = _first(value, ("score", "value", "得分"))
    if value is _MISSING or value is None or isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score):
        return None
    return min(100.0, max(0.0, score))


def _status_label(temperature: Mapping[str, Any]) -> str:
    value = _first(temperature, ("status", "state", "status_label", "状态", "状态标签"))
    if value is _MISSING or value is None or not str(value).strip():
        return "数据不足"
    return _ellipsize(str(value).strip(), 22)


def _contradictions(temperature: Mapping[str, Any]) -> list[str]:
    raw = _first(
        temperature,
        (
            "core_tensions",
            "contradictions",
            "core_contradictions",
            "conflicts",
            "核心矛盾",
        ),
    )
    if raw is _MISSING or raw is None:
        return []
    if isinstance(raw, str):
        candidates: Sequence[Any] = [raw]
    elif isinstance(raw, Mapping):
        candidates = list(raw.values())
    elif isinstance(raw, Sequence) and not isinstance(raw, bytes):
        candidates = raw
    else:
        candidates = [raw]

    result: list[str] = []
    for item in candidates:
        if isinstance(item, Mapping):
            item = _first(
                cast(Mapping[str, Any], item),
                ("text", "description", "summary", "title", "内容"),
            )
        if item is _MISSING or item is None:
            continue
        text = " ".join(str(item).split())
        if text:
            result.append(text)
        if len(result) == 2:
            break
    return result


def _first(source: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in source:
            return source[alias]
    return _MISSING


def _format_score(score: float | None) -> str:
    if score is None:
        return "N/A"
    if float(score).is_integer():
        return str(int(score))
    return f"{score:.1f}"


def _score_color(score: float | None) -> str:
    if score is None:
        return _MUTED
    if score >= 65:
        return UP
    if score >= 35:
        return YELLOW
    return DOWN


def _fragility_color(score: float | None) -> str:
    if score is None:
        return _MUTED
    if score >= 55:
        return "#f06595"
    if score >= 35:
        return YELLOW
    return "#51cf66"


def _status_color(heat: float | None, fragility: float | None) -> str:
    if heat is None and fragility is None:
        return _MUTED
    if fragility is not None and fragility >= 55:
        return "#f06595"
    return _score_color(heat)


def _display_date(trade_date: str) -> str:
    if len(trade_date) == 8 and trade_date.isdigit():
        return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    return trade_date


def _ellipsize(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def run(argv: Sequence[str] | None = None) -> int:
    """Render a market-temperature chart from an evening-review JSON file."""
    parser = argparse.ArgumentParser(description="Render A-share market temperature chart")
    parser.add_argument("--review-json", required=True, help="Structured evening review JSON")
    parser.add_argument("--date", help="Trade date override, YYYYMMDD")
    parser.add_argument(
        "--out",
        default="out/a_share_daily/daily_sentiment_chart.png",
        help="Output PNG path",
    )
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.review_json).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, Mapping):
        parser.error("review JSON must be an object")
    temperature = payload.get("market_temperature", payload)
    if not isinstance(temperature, Mapping):
        parser.error("review JSON does not contain a market_temperature object")
    trade_date = str(args.date or temperature.get("trade_date") or payload.get("trade_date") or "")
    if not trade_date:
        parser.error("trade date is required in --date or review JSON")
    print(generate_market_temperature(temperature, trade_date, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
