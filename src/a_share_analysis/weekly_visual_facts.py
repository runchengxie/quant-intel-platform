"""Read already-published weekly prose facts without recomputing research metrics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NUMBER = r"[+−-]?\d+(?:\.\d+)?"


@dataclass(frozen=True)
class Outcome:
    weeks: int
    median: float
    win_rate: float
    samples: int


@dataclass(frozen=True)
class Method:
    name: str
    date: str
    ret12: float
    percentile: float
    ret52: float
    drawdown: float


@dataclass(frozen=True)
class WeeklyFacts:
    market: dict[str, float] = field(default_factory=dict)
    outcomes: tuple[Outcome, ...] = ()
    methods: tuple[Method, ...] = ()
    observations: tuple[str, ...] = ()
    sample_note: str = ""
    crowding: dict[str, float] = field(default_factory=dict)


def _market(markdown: str) -> dict[str, float]:
    match = re.search(r"^# 本周市场背景\n(.*?)(?=^# |\Z)", markdown, re.M | re.S)
    if not match:
        return {}
    text = match[1]
    result: dict[str, float] = {}
    days = re.search(r"本周 (\d+) 个交易日[，,](\d+) 天上涨[、，](\d+) 天下跌", text)
    if days:
        result.update(zip(("days", "up", "down"), map(float, days.groups()), strict=True))
        if result["up"] + result["down"] > result["days"] or result["days"] < 1:
            raise ValueError("weekly market day counts are inconsistent")
    patterns = {
        "up_share": rf"日均上涨家数占比\s*({NUMBER})%",
        "mean_return": rf"个股平均涨幅\s*({NUMBER})%",
        "turnover": rf"周总成交额\s*({NUMBER})\s*万亿元",
        "daily_turnover": rf"日均\s*({NUMBER})\s*万亿元",
        "limit_ups": rf"全周涨停\s*({NUMBER})\s*只",
        "daily_limit_ups": rf"日均涨停\s*({NUMBER})\s*只",
        "gold_return": rf"外盘黄金：[^\n]*周涨跌幅为\s*({NUMBER})%",
    }
    for name, pattern in patterns.items():
        found = re.search(pattern, text)
        if found:
            result[name] = float(found[1].replace("−", "-"))
    flow = re.search(rf"全周主力资金净(流入|流出)\s*({NUMBER})\s*亿元", text)
    if flow:
        result["flow"] = float(flow[2]) * (1 if flow[1] == "流入" else -1)
    return result


def parse_weekly_facts(markdown: str) -> WeeklyFacts:
    """Missing facts remain absent; unsupported prose stays as observation labels."""
    outcomes = tuple(
        Outcome(int(w), float(m), float(p), int(n))
        for w, m, p, n in re.findall(
            rf"后续 (\d+) 周：收益中位数\s*({NUMBER})%，正收益比例\s*({NUMBER})%（(\d+) 周样本）",
            markdown,
        )
    )
    for item in outcomes:
        if not 0 <= item.win_rate <= 100 or item.samples < 1:
            raise ValueError("weekly historical sample facts are invalid")
    methods = tuple(
        Method(name.strip(), date, float(r12), float(rank), float(r52), float(dd))
        for name, date, r12, rank, r52, dd in re.findall(
            rf"^- (.+?)（截至 (\d{{4}}-\d{{2}}-\d{{2}})）：过去 12 周累计\s*({NUMBER})%，"
            rf"高于约\s*({NUMBER})% 的历史样本。过去 52 周累计\s*({NUMBER})%，当前回撤\s*({NUMBER})%",
            markdown,
            re.M,
        )
    )
    sample = re.search(r"当前状态共出现 (\d+) 周，分布在 (\d+) 段连续时期", markdown)
    observations: list[str] = []
    selected = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            selected = "下周观察" in line
        elif selected and line.startswith("- "):
            observations.append(line.removeprefix("- "))
    crowding = {}
    for key, label in (("small", "小盘"), ("large", "大盘")):
        found = re.search(rf"{label}拥挤度：\s*({NUMBER})", markdown)
        if found:
            crowding[key] = float(found[1])
            if not 0 <= crowding[key] <= 1:
                raise ValueError("weekly crowding fact must be between zero and one")
    if any(len(rows) > 8 for rows in (outcomes, methods, observations)):
        raise ValueError("weekly facts exceed readable chart capacity")
    return WeeklyFacts(
        market=_market(markdown),
        crowding=crowding,
        outcomes=outcomes,
        methods=methods,
        observations=tuple(observations),
        sample_note=f"同状态 {sample[1]} 周 · {sample[2]} 段连续时期" if sample else "",
    )
