"""StyleReplica-A80B20-v0 tearsheet generator.

Produces chart images (PNG) and an HTML report from daily positions data.
Matches the existing market-intel dark-theme chart style:
  BG=#1a1a2e, FG=#e0e0e0, BARS palette, CJK font, 150 DPI.

Sections:
1. Industry Top 10 — horizontal bar chart
2. Theme distribution — pie chart
3. Industry detail table (industry, count, weight, representatives)
4. Theme detail table (theme, count, weight, representatives)
5. A/B leg comparison table
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

# ── Dark theme constants (matching market-intel charts/theme.py) ────────────────
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

BG = "#1a1a2e"
FG = "#e0e0e0"
UP = "#ff6b6b"
DOWN = "#00d4aa"
PURPLE = "#7b68ee"
YELLOW = "#ffd93d"
BARS = [
    "#00d4aa",
    "#7b68ee",
    "#ff6b6b",
    "#ffd93d",
    "#6bc5ff",
    "#ff922b",
    "#20c997",
    "#f06595",
    "#748ffc",
    "#ffe066",
]
PIE_COLORS = [
    "#00d4aa",
    "#7b68ee",
    "#ff6b6b",
    "#ffd93d",
    "#6bc5ff",
    "#ff922b",
    "#20c997",
]
DPI = 150

# CJK font setup
_CJK_CANDIDATES = [
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-VF.otf",
    "/usr/share/fonts/noto-cjk/NotoSansMonoCJKsc-VF.otf",
    "C:/Windows/Fonts/NotoSansSC-VF.ttf",
    "C:/Windows/Fonts/simhei.ttf",
]
_CJK_PATH = None
for _cand in _CJK_CANDIDATES:
    if Path(_cand).exists():
        _CJK_PATH = _cand
        break
_cjk_font = fm.FontProperties(fname=_CJK_PATH) if _CJK_PATH else None

# Global matplotlib defaults
plt.rcParams.update(
    {
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "axes.edgecolor": "#333",
        "axes.labelcolor": FG,
        "text.color": FG,
        "xtick.color": "#888",
        "ytick.color": FG,
        "grid.color": "#333",
        "grid.alpha": 0.3,
    }
)


# ── Theme labels ───────────────────────────────────────────────────────────────

_THEME_DISPLAY: dict[str, str] = {
    "semiconductor": "半导体/芯片",
    "electronic_components": "元器件/被动件",
    "pcb_ccl": "PCB/覆铜板",
    "chemical_materials": "电子化学品",
    "optical_cpo": "光模块/CPO",
    "datacenter_cooling": "数据中心/温控",
    "minor_metals": "小金属/粉体",
}


def _theme_label(theme_key: object) -> str:
    return _THEME_DISPLAY.get(str(theme_key), str(theme_key))


# ── Chart: Industry Top 10 bar chart ───────────────────────────────────────────


def generate_industry_bar_chart(
    positions: pd.DataFrame,
    output_path: str | Path,
    *,
    top_n: int = 10,
) -> Path | None:
    """Horizontal bar chart of industry stock counts (dark theme)."""
    ind_data = positions[positions["industry"].notna() & (positions["industry"] != "")]
    if ind_data.empty:
        return None

    ind_counts = ind_data["industry"].value_counts().head(top_n)
    names = ind_counts.index.tolist()
    values = ind_counts.values

    fig, ax = plt.subplots(figsize=(10, 5.5))
    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, values, height=0.6, color=BARS[: len(names)], alpha=0.85)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontproperties=_cjk_font, fontsize=11)
    ax.invert_yaxis()
    ax.set_xlabel("股票数量", fontproperties=_cjk_font, fontsize=10, color="#888")
    ax.set_title("行业数量 Top 10", fontproperties=_cjk_font, fontsize=14, pad=12, color=FG)

    for bar, v in zip(bars, values, strict=True):
        ax.text(
            bar.get_width() + 0.3,
            bar.get_y() + bar.get_height() / 2,
            str(v),
            va="center",
            fontsize=10,
            color="#aaa",
            fontproperties=_cjk_font,
        )

    ax.grid(axis="x", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xlim(0, max(values) * 1.18)

    plt.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, facecolor=BG, edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return out


# ── Chart: Theme distribution pie chart ─────────────────────────────────────────


def generate_theme_pie_chart(
    positions: pd.DataFrame,
    output_path: str | Path,
) -> Path | None:
    """Pie chart of A-leg theme distribution (dark theme)."""
    a_pos = positions[positions["leg"].str.contains("A", na=False)]
    theme_counts = a_pos["theme"].value_counts()
    if theme_counts.empty:
        return None

    labels = [_theme_label(t) for t in theme_counts.index]
    values = theme_counts.values

    fig, ax = plt.subplots(figsize=(8, 6))
    _wedges, _texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        colors=PIE_COLORS[: len(values)],
        startangle=90,
        pctdistance=0.78,
        textprops={"fontproperties": _cjk_font, "fontsize": 10, "color": FG},
    )
    for t in autotexts:
        t.set_fontsize(9)
        t.set_color(BG)
        t.set_fontweight("bold")

    ax.set_title("A腿产业链主题分布", fontproperties=_cjk_font, fontsize=14, pad=16, color=FG)

    plt.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, facecolor=BG, edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return out


# ── Markdown table formatters ──────────────────────────────────────────────────


def format_industry_table(positions: pd.DataFrame, top_n: int = 15) -> str:
    """Industry detail table as markdown."""
    ind_data = positions[positions["industry"].notna() & (positions["industry"] != "")]
    if ind_data.empty:
        return ""

    rows: list[dict[str, Any]] = []
    for ind_name, group in ind_data.groupby("industry"):
        count = len(group)
        weight = float(group["weight"].sum())
        reps = "、".join(group["symbol"].head(3).tolist())
        rows.append(
            {"行业": str(ind_name), "股票数量": count, "权重": f"{weight:.1%}", "代表公司": reps}
        )
    rows.sort(key=lambda r: r["股票数量"], reverse=True)

    lines = [
        "| 行业 | 股票数量 | 权重 | 代表公司 |",
        "|------|---------|------|---------|",
    ]
    for r in rows[:top_n]:
        lines.append(f"| {r['行业']} | {r['股票数量']} | {r['权重']} | {r['代表公司']} |")
    return "\n".join(lines)


def format_theme_table(positions: pd.DataFrame) -> str:
    """Theme detail table (A-leg only)."""
    a_pos = positions[positions["leg"].str.contains("A", na=False)]
    theme_data = a_pos[a_pos["theme"].notna()]
    if theme_data.empty:
        return ""

    rows: list[dict[str, Any]] = []
    for theme, group in theme_data.groupby("theme"):
        count = len(group)
        weight = float(group["weight"].sum())
        reps = "、".join(group["symbol"].head(3).tolist())
        rows.append(
            {
                "主题": _theme_label(theme),
                "股票数量": count,
                "权重": f"{weight:.1%}",
                "代表公司": reps,
            }
        )
    rows.sort(key=lambda r: r["股票数量"], reverse=True)

    lines = [
        "| 主题 | 股票数量 | 权重 | 代表公司 |",
        "|------|---------|------|---------|",
    ]
    for r in rows:
        lines.append(f"| {r['主题']} | {r['股票数量']} | {r['权重']} | {r['代表公司']} |")
    return "\n".join(lines)


def format_leg_comparison(positions: pd.DataFrame) -> str:
    """A/B leg comparison table."""
    a_mask = positions["leg"].str.contains("A", na=False)
    b_only = positions["leg"].str.contains("B", na=False) & ~positions["leg"].str.contains(
        "A", na=False
    )
    overlap_mask = positions["leg"] == "A+B"

    a_count = int(a_mask.sum())
    b_count = int(b_only.sum())
    overlap_count = int(overlap_mask.sum())

    a_pos = positions[a_mask]
    a_inds = (
        a_pos["industry"].value_counts().head(3)
        if "industry" in a_pos.columns
        else pd.Series(dtype=int)
    )
    a_ind_str = "、".join(f"{k}({v})" for k, v in a_inds.items()) if not a_inds.empty else "-"

    b_pos = positions[b_only]
    b_inds = (
        b_pos["industry"].value_counts().head(3)
        if "industry" in b_pos.columns
        else pd.Series(dtype=int)
    )
    b_ind_str = "、".join(f"{k}({v})" for k, v in b_inds.items()) if not b_inds.empty else "-"

    lines = [
        "| 组合腿 | 股票数 | 行业结构 | 解读 |",
        "|--------|-------|---------|------|",
        f"| A腿 | {a_count} | {a_ind_str} | AI硬件链核心：高弹性、高波动、偏小盘成长 |",
        f"| B腿 | {b_count} | {b_ind_str} | 全市场低波补充：波动收敛、行业分散 |",
        f"| 重叠 | {overlap_count} | - | 双信号确认，权重 2% |",
    ]
    return "\n".join(lines)


# ── HTML report ─────────────────────────────────────────────────────────────────


def _md_to_html_table(md_table: str) -> str:
    lines = md_table.strip().split("\n")
    if len(lines) < 2:
        return md_table
    html = ["<table>"]
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip("|").split("|")]
        tag = "th" if i in (0, 1) else "td"
        html.append("<tr>")
        for cell in cells:
            html.append(f"<{tag}>{cell}</{tag}>")
        html.append("</tr>")
    html.append("</table>")
    return "\n".join(html)


def generate_html_report(
    positions: pd.DataFrame,
    output_path: str | Path,
    *,
    signal_date: str,
    industry_chart_path: str | None = None,
    theme_chart_path: str | None = None,
) -> Path:
    """Generate a dark-theme HTML tearsheet."""
    today_str = datetime.strptime(signal_date, "%Y%m%d").strftime("%Y-%m-%d")
    total = len(positions)
    a_count = int(positions["leg"].str.contains("A", na=False).sum())
    b_count = int(positions["leg"].str.contains("B", na=False).sum())
    overlap = int((positions["leg"] == "A+B").sum())

    industry_table = format_industry_table(positions)
    theme_table = format_theme_table(positions)
    leg_table = format_leg_comparison(positions)

    chart_html = ""
    if industry_chart_path:
        chart_html += f'<img src="{industry_chart_path}" alt="行业Top10" style="max-width:100%;margin:12px 0;border-radius:6px;">\n'
    if theme_chart_path:
        chart_html += f'<img src="{theme_chart_path}" alt="主题分布" style="max-width:100%;margin:12px 0;border-radius:6px;">\n'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>StyleReplica-A80B20-v0 — {today_str}</title>
<style>
  body {{ font-family: -apple-system, 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif;
         max-width: 960px; margin: 2em auto; background: #1a1a2e; color: #e0e0e0; padding: 1em; }}
  h1 {{ border-bottom: 2px solid #7b68ee; padding-bottom: 0.3em; font-weight: 600; }}
  h2 {{ color: #7b68ee; margin-top: 2em; font-size: 1.2em; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.92em; }}
  th, td {{ border: 1px solid #333; padding: 8px 12px; text-align: left; }}
  th {{ background: #16213e; font-weight: 600; color: #7b68ee; }}
  tr:nth-child(even) {{ background: rgba(22,33,62,0.4); }}
  .kpi {{ display: inline-block; margin: 0 2.5em 1em 0; }}
  .kpi-value {{ font-size: 2.2em; font-weight: bold; }}
  .kpi-label {{ font-size: 0.82em; color: #888; }}
  .note {{ color: #666; font-size: 0.82em; margin-top: 3em; border-top: 1px solid #333; padding-top: 1em; }}
</style>
</head>
<body>

<h1>StyleReplica-A80B20-v0 日频 Tearsheet</h1>
<p>报告日期: {today_str} &nbsp;|&nbsp; 模型版本: v0 &nbsp;|&nbsp; 规则打分 + 主题配额</p>

<h2>持仓结构</h2>
<div class="kpi"><div class="kpi-value" style="color:#e0e0e0">{total}</div><div class="kpi-label">总股票数</div></div>
<div class="kpi"><div class="kpi-value" style="color:#ff6b6b">{a_count}</div><div class="kpi-label">A腿 (进攻)</div></div>
<div class="kpi"><div class="kpi-value" style="color:#00d4aa">{b_count}</div><div class="kpi-label">B腿 (防御)</div></div>
<div class="kpi"><div class="kpi-value" style="color:#ffd93d">{overlap}</div><div class="kpi-label">重叠股票</div></div>

<h2>行业数量 Top 10</h2>
{chart_html}

<h2>行业明细</h2>
{_md_to_html_table(industry_table) if industry_table else "<p>暂无数据</p>"}

<h2>主题明细（A腿）</h2>
{_md_to_html_table(theme_table) if theme_table else "<p>暂无数据</p>"}

<h2>A/B 腿差异</h2>
{_md_to_html_table(leg_table) if leg_table else "<p>暂无数据</p>"}

<p class="note">
  风格模型历史模拟，仅用于展示组合行为，暂未完成完整稳健性及交易可实现性验证。<br>
  StyleReplica-A80B20-v0 | 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</p>

</body>
</html>"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


# ── Full tearsheet pipeline ────────────────────────────────────────────────────


def generate_tearsheet(
    positions: pd.DataFrame,
    output_dir: str | Path,
    *,
    signal_date: str,
) -> dict[str, Path]:
    """Generate complete tearsheet: charts + HTML report.

    Returns dict with keys: industry_chart, theme_chart, html_report.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Path] = {}

    if "industry" in positions.columns:
        chart_path = out / "industry_top10.png"
        result = generate_industry_bar_chart(positions, chart_path)
        if result:
            artifacts["industry_chart"] = result

    if "theme" in positions.columns:
        pie_path = out / "theme_distribution.png"
        result = generate_theme_pie_chart(positions, pie_path)
        if result:
            artifacts["theme_chart"] = result

    html_path = out / "style_replica_tearsheet.html"
    generate_html_report(
        positions,
        html_path,
        signal_date=signal_date,
        industry_chart_path="industry_top10.png" if "industry_chart" in artifacts else None,
        theme_chart_path="theme_distribution.png" if "theme_chart" in artifacts else None,
    )
    artifacts["html_report"] = html_path
    return artifacts
