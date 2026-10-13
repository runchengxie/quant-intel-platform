"""Actual meanings of legacy score keys; keys and arithmetic remain compatible."""

from __future__ import annotations

# metric, Chinese display label, limitation
COMMON = {
    "valuation": ("avg_pe", "市盈率估值", "Heuristic relative to a configured PE baseline."),
    "sentiment": ("market_sentiment", "市场情绪", "Sentiment is not a return forecast."),
    "event": (
        "configured_constant",
        "配置常数",
        "Fixed configuration, not measured event intensity.",
    ),
}
THEMES = {
    "ai": {
        "fundamental": (
            "theme_performance",
            "主题表现",
            "Market performance, not financial fundamentals.",
        ),
        "liquidity": ("avg_ps", "市销率估值", "PS valuation, not trading liquidity or fund flow."),
    },
    "magnificent7": {
        "fundamental": ("market_cap", "市值规模", "Aggregate size, not financial quality."),
        "liquidity": ("avg_ps", "市销率估值", "PS valuation, not trading liquidity or fund flow."),
    },
    "btc": {
        "fundamental": ("configured_constant", "配置常数", "No fundamental data is measured."),
        "valuation": ("futures_basis", "期货基差", "Basis proxy, not intrinsic valuation."),
        "sentiment": ("funding_rate", "资金费率情绪", "Funding rate proxy, not a return forecast."),
        "liquidity": ("etf_net_inflow_musd", "ETF净流入", "Fund flow, not execution liquidity."),
    },
}


def metric_semantics(theme: str, key: str) -> dict[str, object]:
    """Describe one supported legacy dimension without inventing missing evidence."""
    entry = THEMES.get(theme, {}).get(key, COMMON.get(key))
    if entry is None:
        return {}
    metric, label, limitation = entry
    return {
        "metric": metric,
        "label": label,
        "evidence_level": "descriptive",
        "limitations": [limitation, "Not validated as an out-of-sample predictive signal."],
    }
