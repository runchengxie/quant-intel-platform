"""Pure Markdown renderer for the A-share market-temperature section."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, cast

_NA = "N/A"

_DIMENSIONS: tuple[tuple[str, str, frozenset[str]], ...] = (
    (
        "liquidity",
        "流动性",
        frozenset(
            {
                "volume",
                "turnover",
                "liquidity",
                "amount",
                "volume_liquidity",
                "量能",
                "流动性",
                "成交额",
            }
        ),
    ),
    (
        "breadth",
        "广度",
        frozenset({"breadth", "marketbreadth", "advancers", "updown", "广度", "涨跌家数"}),
    ),
    (
        "profit_effect",
        "赚钱效应",
        frozenset(
            {
                "profiteffect",
                "profitability",
                "earningeffect",
                "moneymaking",
                "赚钱效应",
                "赚钱",
            }
        ),
    ),
    (
        "loss_risk",
        "亏钱风险",
        frozenset(
            {"losseffect", "losingeffect", "lossrisk", "loss", "亏钱效应", "亏钱风险", "亏钱"}
        ),
    ),
    (
        "trend_confirmation",
        "趋势确认",
        frozenset(
            {
                "funds",
                "funding",
                "moneyflow",
                "capital",
                "flow",
                "trendconfirmation",
                "资金",
                "资金流",
                "趋势确认",
            }
        ),
    ),
    (
        "rotation_quality",
        "轮动质量",
        frozenset(
            {
                "rotation",
                "rotationquality",
                "sectorrotation",
                "breadthrotation",
                "轮动",
                "轮动质量",
                "板块轮动",
            }
        ),
    ),
)

_METRIC_LABELS = {
    "turnover_vs_median": "成交额/历史中位",
    "turnover_percentile": "成交额分位",
    "breadth_up_ratio": "上涨率",
    "median_return": "个股中位涨跌",
    "turnover_weighted_return": "成交额加权涨跌",
    "vwap_above_ratio": "站上VWAP占比",
    "limit_up_ratio": "涨停率",
    "up5_ratio": "涨幅超5%占比",
    "seal_rate": "封板率",
    "limit_down_ratio": "跌停率",
    "down5_ratio": "跌幅超5%占比",
    "failed_board_ratio": "炸板率",
    "index_positive_ratio": "上涨指数占比",
    "index_median_return": "指数中位涨跌",
    "index_close_position": "指数收盘位置",
    "industry_positive_ratio": "上涨行业占比",
    "industry_median_return": "行业中位涨跌",
    "leadership_concentration": "领涨集中度",
    "flow_positive_stock_ratio": "大单净流入覆盖率",
    "flow_balance_ratio": "大单净额占比",
    "profit_effect_score": "赚钱效应观察分",
    "loss_risk_score": "亏钱风险观察分",
    "liquidity_score": "流动性观察分",
    "breadth_score": "广度观察分",
}

_SCORE_METRICS = frozenset(
    {"profit_effect_score", "loss_risk_score", "liquidity_score", "breadth_score"}
)
_RATIO_METRICS = frozenset(_METRIC_LABELS) - {"turnover_vs_median"} - _SCORE_METRICS


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _display_text(value: Any) -> str:
    text = _clean_text(value)
    return text or _NA


def _table_text(value: Any) -> str:
    return _display_text(value).replace("|", r"\|")


def _score_text(value: Any) -> str:
    if isinstance(value, Mapping):
        value = _first(value, "score", "value", "observation_score")
    if value is None or isinstance(value, bool):
        return _NA
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _display_text(value)
    if not math.isfinite(number):
        return _NA
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_token(value: Any) -> str:
    text = _clean_text(value).casefold()
    return "".join(character for character in text if character.isalnum())


def _value_text(value: Any) -> str:
    if isinstance(value, Mapping):
        parts = []
        for key, item in value.items():
            metric_key = str(key)
            key_text = _METRIC_LABELS.get(metric_key, _clean_text(key))
            item_text = (
                _metric_value_text(metric_key, item)
                if metric_key in _METRIC_LABELS
                else _value_text(item)
            )
            if key_text and item_text != _NA:
                parts.append(f"{key_text}: {item_text}")
        return "；".join(parts) or _NA
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_clean_text(item) for item in value if _clean_text(item)]
        return "；".join(parts) or _NA
    return _display_text(value)


def _dimension_entries(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        entries: list[Mapping[str, Any]] = []
        for key, item in value.items():
            if isinstance(item, Mapping):
                entry = dict(item)
                entry.setdefault("key", key)
            else:
                entry = {"key": key, "score": item}
            entries.append(entry)
        return entries
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _find_dimension(
    entries: Sequence[Mapping[str, Any]], aliases: frozenset[str]
) -> Mapping[str, Any]:
    normalized_aliases = {_normalize_token(alias) for alias in aliases}
    for entry in entries:
        key = _normalize_token(_first(entry, "key", "id", "name"))
        label = _normalize_token(entry.get("label"))
        if key in normalized_aliases or label in normalized_aliases:
            return entry
    return {}


def _dimension_status(entry: Mapping[str, Any]) -> str:
    supplied = _first(entry, "status", "state", "signal", "interpretation")
    if supplied is not None:
        return _table_text(supplied)
    score = _number(_first(entry, "score", "value", "observation_score"))
    if score is None:
        return _NA
    higher_is_risk = _normalize_token(entry.get("polarity")) in {
        "higherisrisk",
        "risk",
        "higherrisk",
    }
    if higher_is_risk:
        if score >= 70:
            return "高风险"
        if score >= 55:
            return "风险偏高"
        if score >= 40:
            return "风险中性"
        if score >= 25:
            return "风险偏低"
        return "低风险"
    if score >= 70:
        return "较强"
    if score >= 55:
        return "偏强"
    if score >= 40:
        return "中性"
    if score >= 25:
        return "偏弱"
    return "较弱"


def _metric_value_text(key: str, value: Any) -> str:
    number = _number(value)
    if number is None:
        return _NA
    if key == "turnover_vs_median":
        return f"{number:.2f}x"
    if key in _SCORE_METRICS:
        score = number * 100 if abs(number) <= 1 else number
        return _score_text(score)
    if key in _RATIO_METRICS:
        return f"{number:.1%}"
    return _score_text(number)


def _dimension_evidence(entry: Mapping[str, Any]) -> str:
    supplied = _first(entry, "evidence", "facts", "detail", "note")
    if supplied is not None:
        return _value_text(supplied).replace("|", r"\|")
    metrics = _mapping(entry.get("metrics"))
    parts: list[str] = []
    for key, value in metrics.items():
        value_text = _metric_value_text(str(key), value)
        if value_text == _NA:
            continue
        label = _METRIC_LABELS.get(str(key), _clean_text(key))
        parts.append(f"{label} {value_text}")
        if len(parts) >= 3:
            break
    return "；".join(parts).replace("|", r"\|") or _NA


def _render_dimensions(payload: Mapping[str, Any]) -> list[str]:
    raw_dimensions = _first(payload, "dimensions", "six_dimensions", "dimension_scores")
    entries = _dimension_entries(raw_dimensions)
    lines = [
        "### 六维观察",
        "",
        "| 维度 | 观察分 | 状态 | 证据 |",
        "|---|---:|---|---|",
    ]
    for _key, label, aliases in _DIMENSIONS:
        entry = _find_dimension(entries, aliases)
        rendered_label = _table_text(entry.get("label") or label) if entry else label
        score = _score_text(_first(entry, "score", "value", "observation_score"))
        status = _dimension_status(entry)
        evidence = _dimension_evidence(entry)
        lines.append(f"| {rendered_label} | {score} | {status} | {evidence} |")
    return lines


def _has_known_item_fields(value: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return any(key in value for key in keys)


def _collect_raw_items(value: Any, known_keys: Sequence[str]) -> list[Any]:
    """Normalise the incoming value into a flat list of renderable items."""
    if isinstance(value, Mapping):
        if _has_known_item_fields(value, known_keys):
            return [value]
        return [
            f"{_clean_text(key)}: {_value_text(item)}"
            for key, item in value.items()
            if _clean_text(key)
        ]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    if value is None:
        return []
    return [value]


def _render_one_item(
    item: Any,
    *,
    primary_keys: Sequence[str],
    detail_fields: Sequence[tuple[str, Sequence[str]]],
) -> str | None:
    """Render a single item into a joined text line, or None if empty."""
    if not isinstance(item, Mapping):
        text = _clean_text(item)
        return text or None

    typed_item = cast(Mapping[str, Any], item)
    primary = _clean_text(_first(typed_item, *primary_keys))
    parts = [primary] if primary else []
    for label, keys in detail_fields:
        detail = _first(typed_item, *keys)
        detail_text = _value_text(detail) if detail is not None else ""
        if detail_text and detail_text != _NA:
            parts.append(f"{label}: {detail_text}")
    if not parts:
        generic = _value_text(item)
        if generic != _NA:
            parts.append(generic)
    if parts:
        return "；".join(parts)
    return None


def _section_items(
    value: Any,
    *,
    primary_keys: Sequence[str],
    detail_fields: Sequence[tuple[str, Sequence[str]]],
) -> list[str]:
    known_keys = tuple(primary_keys) + tuple(key for _label, keys in detail_fields for key in keys)
    raw_items = _collect_raw_items(value, known_keys)

    rendered: list[str] = []
    for item in raw_items:
        line = _render_one_item(item, primary_keys=primary_keys, detail_fields=detail_fields)
        if line:
            rendered.append(line)
    return rendered


def _render_list_section(title: str, items: Sequence[str]) -> list[str]:
    lines = [f"### {title}"]
    if not items:
        lines.append(f"- {_NA}")
        return lines
    lines.extend(f"- {item}" for item in items)
    return lines


def _render_core_tensions(payload: Mapping[str, Any]) -> list[str]:
    value = _first(payload, "core_tensions", "core_conflicts", "tensions", "contradictions")
    items = _section_items(
        value,
        primary_keys=("tension", "summary", "text", "description", "label", "name"),
        detail_fields=(
            ("证据", ("evidence", "facts")),
            ("含义", ("implication", "impact", "interpretation")),
        ),
    )
    return _render_list_section("核心矛盾", items)


def _condition_rule(item: Mapping[str, Any]) -> str:
    metric_key = _clean_text(item.get("metric"))
    operator = _clean_text(item.get("operator"))
    target = _metric_value_text(metric_key, item.get("target"))
    if not metric_key or not operator or target == _NA:
        return ""
    metric = _METRIC_LABELS.get(metric_key, metric_key)
    return f"{metric} {operator} {target}"


def _with_condition_rules(value: Any) -> Any:
    def augment(item: Any) -> Any:
        if not isinstance(item, Mapping):
            return item
        augmented = dict(item)
        rule = _condition_rule(item)
        if rule:
            augmented["condition_rule"] = rule
        return augmented

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [augment(item) for item in value]
    return augment(value)


_VALIDATION_STATUS_LABELS = {
    "confirmed": "已验证",
    "invalidated": "未验证",
    "not_evaluable": "不可评估",
}
_VALIDATION_REASON_LABELS = {
    "current_metric_missing": "当前指标缺失",
    "condition_invalid": "验证条件无效",
}


def _with_previous_display(value: Any) -> Any:
    def augment(item: Any) -> Any:
        if not isinstance(item, Mapping):
            return item
        augmented = dict(item)
        status = _clean_text(item.get("status"))
        if status in _VALIDATION_STATUS_LABELS:
            augmented["validation_result"] = _VALIDATION_STATUS_LABELS[status]
        metric = _clean_text(item.get("metric"))
        if metric and item.get("observed") is not None:
            augmented["observed_display"] = _metric_value_text(metric, item.get("observed"))
        reason = _clean_text(item.get("reason"))
        if reason in _VALIDATION_REASON_LABELS:
            augmented["reason_display"] = _VALIDATION_REASON_LABELS[reason]
        return augmented

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [augment(item) for item in value]
    return augment(value)


def _render_validation_conditions(payload: Mapping[str, Any]) -> list[str]:
    value = _first(
        payload,
        "validation_conditions",
        "tomorrow_validation",
        "tomorrow_checks",
        "next_day_checks",
    )
    items = _section_items(
        _with_condition_rules(value),
        primary_keys=("condition", "check", "item", "text", "summary", "description", "metric"),
        detail_fields=(
            ("确认", ("confirm_if", "pass_if", "trigger", "threshold")),
            ("失效", ("invalidate_if", "fail_if", "invalidation", "negative_if")),
            ("条件", ("condition_rule",)),
            ("说明", ("implication", "note")),
        ),
    )
    return _render_list_section("明日验证", items)


def _render_previous_validation(payload: Mapping[str, Any]) -> list[str]:
    value = _first(
        payload,
        "previous_validation",
        "yesterday_validation",
        "previous_checks",
        "validation_review",
    )
    items = _section_items(
        _with_previous_display(_with_condition_rules(value)),
        primary_keys=(
            "claim",
            "hypothesis",
            "item",
            "check",
            "text",
            "summary",
            "description",
            "metric",
        ),
        detail_fields=(
            ("结果", ("result", "outcome", "validation_result", "status")),
            ("观测", ("observed_display", "observed", "actual")),
            ("证据", ("evidence",)),
            ("条件", ("condition_rule",)),
            ("说明", ("note", "reason_display", "reason")),
        ),
    )
    return _render_list_section("昨日验证复盘", items)


def _calibration_text(value: Any) -> str:
    if not isinstance(value, Mapping):
        if value == "provisional_observation_scale":
            return "暂定观察刻度（未回测）"
        return _display_text(value)

    parts: list[str] = []
    status = _first(value, "status", "state", "label")
    calibrated = value.get("calibrated")
    if status is not None:
        parts.append(_display_text(status))
    elif isinstance(calibrated, bool):
        parts.append("已校准" if calibrated else "未校准")

    version = _first(value, "version", "calibration_version")
    if version is not None:
        parts.append(f"版本 {_display_text(version)}")
    sample_size = _first(value, "sample_size", "samples", "n")
    if sample_size is not None:
        parts.append(f"样本 {_display_text(sample_size)}")
    note = _first(value, "note", "description", "warning")
    if note is not None:
        parts.append(_display_text(note))
    return "；".join(parts) or _NA


def _render_confidence(payload: Mapping[str, Any]) -> list[str]:
    raw_confidence = _first(payload, "confidence", "data_confidence")
    confidence = _mapping(raw_confidence)
    if confidence:
        level = _display_text(_first(confidence, "level", "status", "label"))
        available = _score_text(
            _first(confidence, "available_dimensions", "available", "available_count")
        )
        total = _score_text(_first(confidence, "total_dimensions", "total", "dimension_count"))
        coverage = f"{available}/{total}" if _NA not in (available, total) else _NA
        warnings = _value_text(_first(confidence, "warnings", "issues", "notes"))
    else:
        confidence_number = _number(raw_confidence)
        if confidence_number is None:
            level = _display_text(raw_confidence)
        else:
            confidence_level = (
                "高" if confidence_number >= 0.8 else "中" if confidence_number >= 0.55 else "低"
            )
            level = f"{confidence_level}（{confidence_number:.0%}）"

        dimensions = _dimension_entries(
            _first(payload, "dimensions", "six_dimensions", "dimension_scores")
        )
        computed_warnings: list[str] = []
        if dimensions:
            matched_dimensions = [
                (label, _find_dimension(dimensions, aliases))
                for _key, label, aliases in _DIMENSIONS
            ]
            available_dimensions = sum(
                _number(_first(item, "score", "value", "observation_score")) is not None
                for _label, item in matched_dimensions
            )
            coverage = f"{available_dimensions}/{len(_DIMENSIONS)}"
            missing = [
                _display_text(item.get("label") or label)
                for label, item in matched_dimensions
                if _number(_first(item, "score", "value", "observation_score")) is None
            ]
            if missing:
                computed_warnings.append(f"缺少 {'、'.join(missing)}")
        else:
            coverage = _NA
        supplied_warnings = _first(payload, "data_warnings", "warnings")
        supplied_warning_text = _value_text(supplied_warnings)
        if supplied_warning_text != _NA:
            computed_warnings.append(supplied_warning_text)
        warnings = "；".join(computed_warnings) or _NA

    calibration = _first(payload, "calibration", "calibration_status", "calibration_note")
    return [
        "### 数据完整度与校准",
        f"- 完整度: {level}；六维可用: {coverage}。",
        f"- 警告: {warnings}。",
        f"- 校准: {_calibration_text(calibration)}。",
    ]


def _status_value(payload: Mapping[str, Any]) -> Any:
    value = _first(payload, "status_label", "state_label", "market_state", "status")
    if value is not None:
        if isinstance(value, Mapping):
            return _first(value, "label", "status_label", "state", "name")
        return value
    state = _mapping(payload.get("state"))
    return _first(state, "label", "status_label", "state", "name")


def _composite_score(payload: Mapping[str, Any], name: str) -> Any:
    aliases = {
        "heat": ("heat_score", "heat", "temperature_score", "temperature"),
        "fragility": ("fragility_score", "fragility", "risk_score", "vulnerability_score"),
    }
    value = _first(payload, *aliases[name])
    if value is not None:
        return value
    composite = _mapping(_first(payload, "composite", "scores", "state"))
    return _first(composite, *aliases[name])


def render_market_temperature_section(
    payload: Mapping[str, Any], *, heading: str = "一、市场状态"
) -> list[str]:
    """Render a deterministic market-temperature section from structured observations.

    Missing fields remain visible as ``N/A``. Scores are explicitly observations and are
    never translated into position sizing or trading instructions by this renderer.
    """

    source = payload if isinstance(payload, Mapping) else {}
    heading_text = _clean_text(heading).lstrip("#").strip() or "一、市场状态"
    heat = _score_text(_composite_score(source, "heat"))
    fragility = _score_text(_composite_score(source, "fragility"))

    lines = [
        f"## {heading_text}",
        f"- 状态: {_display_text(_status_value(source))}。",
        f"- 热度 / 脆弱度: {heat} / {fragility}（观察分）。",
        "- 口径: 热度、脆弱度与六维分数均为市场状态观察分，不直接映射仓位，也不构成交易指令。",
        "",
    ]
    sections = (
        _render_dimensions(source),
        _render_core_tensions(source),
        _render_validation_conditions(source),
        _render_previous_validation(source),
        _render_confidence(source),
    )
    for section in sections:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(section)
    return lines


__all__ = ["render_market_temperature_section"]
