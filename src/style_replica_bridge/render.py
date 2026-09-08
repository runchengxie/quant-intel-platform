"""Position rendering for the StyleReplica bridge.

Turns a StyleReplica positions table into the markdown message and Feishu
interactive card consumed by delivery. Pure formatting: no I/O, no network.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

_THEME_LABELS: dict[str, str] = {
    "semiconductor": "半导体/芯片/设备材料",
    "electronic_components": "元器件/被动件/陶瓷",
    "pcb_ccl": "PCB/覆铜板/电子基材",
    "chemical_materials": "电子化学品/高分子材料",
    "optical_cpo": "光模块/CPO/通信",
    "datacenter_cooling": "数据中心/存储/温控",
    "minor_metals": "小金属/稀有金属/粉体",
}


def load_positions(path: str | Path) -> pd.DataFrame:
    """Load positions CSV from a StyleReplica pipeline run."""
    return pd.read_csv(Path(path))


def _build_tags_for_row(row: pd.Series) -> str:
    """Derive the hot-tag string for a single position row."""
    tags: list[str] = []
    leg = str(row.get("leg", ""))
    score_a = row.get("score_a", None)
    score_b = row.get("score_b", None)
    theme = row.get("theme", "")
    industry = row.get("industry", "")

    if leg and "A" in leg:
        if score_a is not None and not pd.isna(score_a):
            sa = float(score_a)
            if sa >= 0.85:
                tags.append("高弹性")
            elif sa >= 0.70:
                tags.append("活跃成长")
            else:
                tags.append("成长")
        theme_str = str(theme) if theme and str(theme) != "nan" else ""
        label = _THEME_LABELS.get(theme_str, "")
        if label:
            tags.append(label)
    elif leg and "B" in str(leg):
        if score_b is not None and not pd.isna(score_b):
            sb = float(score_b)
            if sb >= 0.65:
                tags.append("波动收敛")
            elif sb >= 0.50:
                tags.append("低波防御")
        ind_str = str(industry) if industry and str(industry) != "nan" else ""
        if ind_str:
            tags.append(ind_str)
    else:
        tags.append("量化筛选")

    return " · ".join(tags[:3])


def enrich_positions_with_tags(
    positions: pd.DataFrame,
) -> pd.DataFrame:
    """Add human-readable hot tags explaining why each stock was selected.

    Tags are derived from the model's factor profile and theme assignment:
    - A-leg stocks get theme label + style tags (高弹性/活跃成长)
    - B-leg stocks get industry + style tags (波动收敛/低波防御)

    Also adds a 'concepts' column for compatibility (empty, can be enriched
    later via API when concept data is accessible).
    """
    positions = positions.copy()
    positions["concepts"] = ""

    positions["hot_tags"] = [_build_tags_for_row(row) for _, row in positions.iterrows()]
    return positions


def _render_industry_section(positions: pd.DataFrame, total: int) -> list[str]:
    if "industry" not in positions.columns:
        return []
    ind_data = positions[positions["industry"].notna() & (positions["industry"] != "")]
    if ind_data.empty:
        return []
    ind_counts = ind_data["industry"].value_counts().head(8)
    lines = ["**行业 Top 8**"]
    for ind, cnt in ind_counts.items():
        pct = cnt / total * 100
        lines.append(f"  {ind}: {cnt} 只 ({pct:.1f}%)")
    return lines


def _render_theme_section(positions: pd.DataFrame, a_mask: pd.Series) -> list[str]:
    if "theme" not in positions.columns:
        return []
    theme_counts = positions[a_mask]["theme"].value_counts()
    if theme_counts.empty:
        return []
    lines = ["**A腿主题分布**"]
    for theme, cnt in theme_counts.items():
        label = _THEME_LABELS.get(str(theme), str(theme))
        lines.append(f"  {label}: {cnt} 只")
    return lines


def _render_tag_cloud_section(positions: pd.DataFrame) -> list[str]:
    if "hot_tags" not in positions.columns:
        return []
    all_tags: list[str] = []
    for tags_str in positions["hot_tags"].dropna():
        for tag in str(tags_str).split(" · "):
            tag = tag.strip()
            if tag:
                all_tags.append(tag)
    if not all_tags:
        return []
    tag_counts = Counter(all_tags).most_common(12)
    tag_parts = [f"{tag}({cnt})" for tag, cnt in tag_counts]
    return ["**持仓风格标签**", "  " + "  ".join(tag_parts)]


def _render_picks_section(
    positions: pd.DataFrame,
    mask: pd.Series,
    score_col: str,
    title: str,
) -> list[str]:
    if score_col not in positions.columns:
        return []
    top = positions[mask].nlargest(5, score_col)
    if top.empty:
        return []
    lines = [title]
    for _, row in top.iterrows():
        score = row.get(score_col, "-")
        tags = row.get("hot_tags", "")
        tag_str = f"  [{tags}]" if tags else ""
        lines.append(f"  {row['symbol']}  score={score:.3f}{tag_str}")
    return lines


def _append_section(lines: list[str], section: list[str]) -> None:
    """Append a rendered section and a single blank separator line.

    A falsy (empty) section contributes nothing, preserving the original
    behaviour where missing optional columns produced no blank line.
    """
    if not section:
        return
    lines.extend(section)
    lines.append("")


def format_holdings_summary(positions: pd.DataFrame, signal_date: str) -> str:
    """Format positions into a concise, readable markdown message for Feishu.

    Sections (each rendered by a dedicated ``_render_*_section`` helper):
    1. Header with date and model version
    2. Summary stats (total stocks, A/B counts, overlap)
    3. Industry Top 8
    4. A-leg theme distribution
    5. Hot tag cloud (top tags across all positions)
    6. A-leg top 5 picks with tags
    7. B-leg top 5 picks with tags
    """
    today_str = datetime.strptime(signal_date, "%Y%m%d").strftime("%Y-%m-%d")
    a_mask = positions["leg"].str.contains("A", na=False)
    b_mask = positions["leg"].str.contains("B", na=False)
    a_count = int(a_mask.sum())
    b_count = int(b_mask.sum())
    overlap = int((positions["leg"] == "A+B").sum())
    total = len(positions)
    total_weight = float(positions["weight"].sum())

    lines = [
        "**StyleReplica-A80B20-v0 日频持仓**",
        f"{today_str}  |  总股票 {total} 只  |  总权重 {total_weight:.0%}",
        "",
        "**持仓结构**",
        f"  A腿 (进攻/硬件链): {a_count} 只  |  B腿 (防御/低波): {b_count} 只",
        f"  重叠: {overlap} 只  |  单票常规权重: 1%  |  重叠票: 2%",
        "",
    ]

    _append_section(lines, _render_industry_section(positions, total))
    _append_section(lines, _render_theme_section(positions, a_mask))
    _append_section(lines, _render_tag_cloud_section(positions))
    _append_section(
        lines, _render_picks_section(positions, a_mask, "score_a", "**A腿 Top 5 (按得分)**")
    )
    _append_section(
        lines,
        _render_picks_section(positions, b_mask & ~a_mask, "score_b", "**B腿 Top 5 (按得分)**"),
    )

    lines.append(
        "---\n"
        "> 风格模型历史模拟，仅用于展示组合行为。\n"
        "> 模型: StyleReplica-A80B20-v0 | 规则打分 + 主题配额 + 日频缓冲"
    )

    return "\n".join(lines)


def format_feishu_card(positions: pd.DataFrame, signal_date: str) -> dict[str, Any]:
    """Build a Feishu interactive card payload."""
    today_str = datetime.strptime(signal_date, "%Y%m%d").strftime("%Y-%m-%d")
    total = len(positions)
    a_count = int(positions["leg"].str.contains("A", na=False).sum())
    b_count = int(positions["leg"].str.contains("B", na=False).sum())

    a_top = positions[positions["leg"].str.contains("A", na=False)]
    if "score_a" in a_top.columns:
        a_top = a_top.nlargest(5, "score_a")
    a_tags = [
        {"tag": "text", "text": f"  {r['symbol']}  [{r.get('hot_tags', '')}]\n"}
        for _, r in a_top.iterrows()
    ]

    b_pos = positions[
        positions["leg"].str.contains("B", na=False) & ~positions["leg"].str.contains("A", na=False)
    ]
    if "score_b" in b_pos.columns:
        b_pos = b_pos.nlargest(5, "score_b")
    b_tags = [
        {"tag": "text", "text": f"  {r['symbol']}  [{r.get('hot_tags', '')}]\n"}
        for _, r in b_pos.iterrows()
    ]

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"StyleReplica-A80B20 持仓 {today_str}"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": f"**总持仓 {total} 只**  |  A腿 {a_count} / B腿 {b_count}\n---",
                },
                {
                    "tag": "markdown",
                    "content": f"**A腿 Top 5**\n{''.join(t['text'] for t in a_tags)}",
                },
                {
                    "tag": "markdown",
                    "content": f"**B腿 Top 5**\n{''.join(t['text'] for t in b_tags)}",
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "StyleReplica-A80B20-v0 | 规则打分 + 主题配额",
                        }
                    ],
                },
            ],
        },
    }
