"""Topic weight bar chart from the DailyWatch20 topic summary artifact."""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..topic_summary import TopicSummaryError, load_topic_summary
from .theme import (
    ACCENT,
    BG,
    FG,
    MUTED,
    add_report_header,
    cjk,
    cjk_heavy,
    style_plot_axes,
)

_TOPIC_LABEL_ALIASES = {
    "hotspot": "热点",
    "hotspots": "热点",
    "hot spot": "热点",
    "hot spots": "热点",
    "hot sector": "热点板块",
    "hot sectors": "热点板块",
    "hot concept": "热点概念",
    "hot concepts": "热点概念",
    "topic": "主题",
    "topics": "主题",
    "theme": "主题",
    "themes": "主题",
    "ai": "人工智能",
    "artificial intelligence": "人工智能",
    "infrastructure": "基础设施",
    "semiconductor": "半导体",
    "semiconductors": "半导体",
    "chip": "芯片",
    "chips": "芯片",
    "robotics": "机器人",
    "robot": "机器人",
    "new energy": "新能源",
    "electric vehicle": "新能源汽车",
    "electric vehicles": "新能源汽车",
    "ev": "新能源汽车",
    "evs": "新能源汽车",
    "data center": "数据中心",
    "data centers": "数据中心",
    "cloud computing": "云计算",
    "consumer electronics": "消费电子",
    "low altitude economy": "低空经济",
    "optical communication": "光通信",
    "pharmaceutical": "医药",
    "pharmaceuticals": "医药",
    "biotech": "生物医药",
}

_TOPIC_PHRASE_REPLACEMENTS = tuple(
    sorted(_TOPIC_LABEL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
)


def format_topic_label(value: object) -> str:
    """Return a chart-display label without changing the upstream topic contract."""
    text = str(value or "").strip()
    if not text:
        return "未命名主题"

    normalized = re.sub(r"[_-]+", " ", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    alias = _TOPIC_LABEL_ALIASES.get(normalized.lower())
    if alias:
        return alias

    rendered = normalized
    for phrase, replacement in _TOPIC_PHRASE_REPLACEMENTS:
        rendered = re.sub(
            rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])",
            replacement,
            rendered,
            flags=re.IGNORECASE,
        )
    rendered = re.sub(r"\s+", " ", rendered).strip()
    rendered = re.sub(r"\s*([/|+&、，,])\s*", r"\1", rendered)
    rendered = rendered.replace("&", "/")
    return rendered or "未命名主题"


def generate_topic(
    topic_summary_json_path: str, out_path: str = "out/a_share_daily/daily_topic_chart.png"
) -> str | None:
    """Generate a DailyWatch20 topic-weight chart. Returns path or None on failure."""
    try:
        data = load_topic_summary(Path(topic_summary_json_path))
    except TopicSummaryError:
        return None
    topics = data.get("topics", [])
    if not topics:
        return None

    topics_sorted = sorted(topics, key=lambda t: t["weight"], reverse=True)[:10]
    names = [format_topic_label(t.get("topic")) for t in topics_sorted]
    weights = [t["weight"] for t in topics_sorted]

    report_date = str(data.get("signal_date") or data.get("source_date") or "")
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=BG)
    add_report_header(
        fig,
        title="DailyWatch20 热点主题分布",
        kicker=f"{report_date} · A股日报" if report_date else "A股日报",
        subtitle="入选股票主题按跟踪权重聚合",
    )
    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, weights, height=0.6, color=ACCENT, alpha=0.82)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontproperties=cjk_heavy, fontsize=12)
    ax.set_xlabel("主题权重", fontproperties=cjk, fontsize=11, color=MUTED)
    ax.set_title(
        "热点主题权重 Top 10",
        loc="left",
        fontproperties=cjk_heavy,
        fontsize=11.5,
        pad=9,
        color=FG,
    )
    ax.invert_yaxis()

    for bar, w in zip(bars, weights, strict=False):
        ax.text(
            bar.get_width() + 0.005,
            bar.get_y() + bar.get_height() / 2,
            f"{w:.3f}",
            va="center",
            fontsize=10,
            color=MUTED,
        )
    ax.set_xlim(0, max(weights) * 1.2)
    style_plot_axes(ax, grid_axis="x")

    fig.subplots_adjust(left=0.18, right=0.95, top=0.78, bottom=0.14)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=BG, edgecolor="none")
    plt.close(fig)
    return str(out_path)
