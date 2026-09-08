"""Client-safe DailyWatch20 renderers without internal sleeve or score details."""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pandas as pd

from .daily_watch20 import (
    DailyWatch20Artifact,
    DailyWatch20ValidationError,
    _date_dash,
    _records,
    _regime_summary,
    _split_tokens,
    _truncate,
)

CLIENT_DISCLAIMER = "仅供研究观察，不构成投资建议或买卖指令。"
CLIENT_METHOD_FACTORS = "估值、价格动量、流动性、多周期及下行波动、波动收敛、分钟级量价与稳定性"
CLIENT_METHOD_SUMMARY = f"模型结合{CLIENT_METHOD_FACTORS}特征"
_CLIENT_TABLE_COLUMN_WIDTHS = (0.075, 0.235, 0.25, 0.425)
_CLIENT_TABLE_DISPLAY_CAPACITY = 58
_CLIENT_CONSTRUCTION_HINT_PATTERNS = (
    ("split counts", re.compile(r"(?<![A-Za-z0-9])(?:A\s*4|B\s*16)(?![A-Za-z0-9])", re.I)),
    ("split ratio", re.compile(r"(?<!\d)4\s*(?:\+|/|／)\s*16(?!\d)")),
    ("split labels", re.compile(r"(?<![A-Za-z0-9])A\s*[/／]\s*B(?![A-Za-z0-9])", re.I)),
    ("leg or group labels", re.compile(r"[AB]\s*(?:腿|组|池)", re.I)),
    (
        "dual construction",
        re.compile(
            r"(?:两|双)(?:条|个|种|类)?(?:腿|持仓|组合|选股池)"
            r"|(?:两路|双路)(?:选股|构造|筛选|组合)?"
            r"|(?:拼接|拼合)(?:选股池|清单|持仓|组合)"
        ),
    ),
    (
        "internal field",
        re.compile(
            r"(?<![A-Za-z0-9_])(?:sleeve|guarded\s*16|xgb_score|guard_score|tracking_weight)"
            r"(?![A-Za-z0-9_])",
            re.I,
        ),
    ),
    ("internal role", re.compile(r"模型探索|约束观察|进攻[/／]硬件链|防御[/／]低波")),
)
_CLIENT_UNSUPPORTED_FEATURE_PATTERNS = (
    ("earnings quality", re.compile(r"盈利质量|earnings\s+quality", re.I)),
    (
        "individual market beta",
        re.compile(
            r"(?:个股|股票)(?:的)?(?:市场)?\s*(?:beta|β)|市场\s*(?:beta|β)",
            re.I,
        ),
    ),
    (
        "fundamental growth",
        re.compile(r"基本面(?:成长|增长)|(?:营收|利润)(?:增长|成长)(?:因子|特征|指标)", re.I),
    ),
    (
        "volatility change rate",
        re.compile(r"波动率?(?:的)?变化率|volatility\s+change\s+rate", re.I),
    ),
)


def validate_daily_watch20_client_copy(text: str) -> str:
    """Fail closed on internal construction hints or unsupported feature claims."""

    normalized = unicodedata.normalize("NFKC", text)
    for label, pattern in _CLIENT_CONSTRUCTION_HINT_PATTERNS:
        if pattern.search(normalized):
            raise DailyWatch20ValidationError(
                f"client copy exposes an internal DailyWatch20 construction hint: {label}"
            )
    for label, pattern in _CLIENT_UNSUPPORTED_FEATURE_PATTERNS:
        if pattern.search(normalized):
            raise DailyWatch20ValidationError(
                f"client copy claims an unsupported DailyWatch20 feature: {label}"
            )
    return text


def client_display_frame(artifact: DailyWatch20Artifact) -> pd.DataFrame:
    """Return a deterministic, explicitly non-ranked client display order."""

    frame = artifact.frame.sort_values(
        ["industry", "theme", "symbol"],
        ascending=True,
        kind="mergesort",
    ).reset_index(drop=True)
    frame["display_no"] = range(1, len(frame) + 1)
    return frame


def _validate_client_frame_copy(
    artifact: DailyWatch20Artifact,
    frame: pd.DataFrame,
) -> None:
    visible_copy = [CLIENT_METHOD_SUMMARY, _regime_summary(artifact.receipt)]
    for column in ("symbol", "name", "industry", "theme", "top_drivers", "primary_risk"):
        visible_copy.extend(str(value) for value in frame[column].tolist())
    validate_daily_watch20_client_copy("\n".join(visible_copy))


def _group_share(frame: pd.DataFrame, column: str, *, limit: int) -> pd.Series:
    labels = frame[column].replace("", "未分类")
    counts = cast(pd.Series, labels.value_counts(sort=True))
    shares = counts.astype(float).div(max(len(frame), 1))
    if len(shares) <= limit:
        return shares
    head = shares.iloc[:limit].copy()
    head.loc["其他"] = float(shares.iloc[limit:].sum())
    return head


def _short_tokens(value: Any, *, limit: int = 2, width: int = 18) -> str:
    tokens = list(dict.fromkeys(_split_tokens(value)))[:limit]
    return _truncate("、".join(tokens) or "未提供", width)


def _display_width(value: Any) -> int:
    text = str(value or "")
    return sum(2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1 for char in text)


def _display_prefix(text: str, width: int) -> str:
    used = 0
    chars: list[str] = []
    for char in text:
        char_width = _display_width(char)
        if used + char_width > width:
            break
        chars.append(char)
        used += char_width
    return "".join(chars)


def _truncate_display(value: Any, width: int) -> str:
    text = str(value or "-").strip()
    if _display_width(text) <= width:
        return text
    ellipsis = "…"
    return _display_prefix(text, max(width - _display_width(ellipsis), 0)).rstrip() + ellipsis


def _wrap_display_text(value: Any, *, width: int, max_lines: int) -> list[str]:
    remaining = str(value or "-").strip()
    lines: list[str] = []
    break_chars = {"、", "/", "|"}
    while remaining and len(lines) < max_lines:
        if _display_width(remaining) <= width:
            lines.append(remaining)
            break
        if len(lines) == max_lines - 1:
            lines.append(_truncate_display(remaining, width))
            break

        prefix = _display_prefix(remaining, width)
        split_at = max(
            (index + 1 for index, char in enumerate(prefix) if char in break_chars),
            default=0,
        )
        if split_at:
            line = prefix[:split_at].rstrip(" 、/|")
            remaining = remaining[split_at:].lstrip(" 、/|")
        else:
            line = prefix
            remaining = remaining[len(prefix) :].lstrip()
        lines.append(line)
    return lines or ["-"]


def _client_table_display_budget(column: int) -> int:
    return max(4, int(_CLIENT_TABLE_DISPLAY_CAPACITY * _CLIENT_TABLE_COLUMN_WIDTHS[column]))


def _png_reason_risk_text(drivers: Any, risk: Any) -> str:
    width = _client_table_display_budget(3)
    driver_tokens = list(dict.fromkeys(_split_tokens(drivers)))[:2]
    risk_tokens = list(dict.fromkeys(_split_tokens(risk)))[:1]
    driver_text = "关注 " + ("、".join(driver_tokens) or "未提供")
    risk_text = "风险 " + ("、".join(risk_tokens) or "未提供")
    lines = _wrap_display_text(driver_text, width=width, max_lines=2)
    lines.extend(_wrap_display_text(risk_text, width=width, max_lines=2))
    return "\n".join(lines)


def _client_minute_text(receipt: Mapping[str, Any]) -> str:
    minute = receipt.get("minute_features")
    if not isinstance(minute, Mapping) or not bool(minute.get("enabled")):
        return "分钟输入未启用"
    as_of = str(minute.get("as_of") or "未标注")
    return f"分钟输入 as-of {as_of}，已通过日期与完整性门禁"


def _client_candidate_data_warning(receipt: Mapping[str, Any]) -> str:
    candidate_pool = receipt.get("candidate_pool")
    if not isinstance(candidate_pool, Mapping):
        return ""
    missing = candidate_pool.get("missing_ranks")
    if candidate_pool.get("rank_coverage_status") != "degraded" or not isinstance(missing, list):
        return ""
    ranks = [str(rank) for rank in missing if type(rank) is int and rank > 0]
    if not ranks:
        return ""
    return (
        "⚠️ 数据完整性提示：TuShare 数据服务商疑似缺失部分热榜数据"
        f"（排名 {'、'.join(ranks)}）。本期已按其余经审计数据生成，缺失排名未补号。"
    )


def _share_text(shares: pd.Series, *, limit: int = 5) -> str:
    return " · ".join(
        f"{_truncate(label, 10)} {float(value):.0%}" for label, value in shares.iloc[:limit].items()
    )


def _client_html_rows(frame: pd.DataFrame) -> str:
    rows: list[str] = []
    for row in _records(frame):
        state = "新增" if bool(row["is_new"]) else "保留"
        state_class = "state-new" if bool(row["is_new"]) else "state-kept"
        rows.append(
            "<tr>"
            f"<td>{int(row['display_no'])}</td>"
            f"<td><strong>{html.escape(str(row['name']))}</strong>"
            f"<small>{html.escape(str(row['symbol']))}</small></td>"
            f"<td>{html.escape(str(row['industry'] or '未分类'))}</td>"
            f"<td>{html.escape(str(row['theme'] or '未分类'))}</td>"
            f"<td>{html.escape(_short_tokens(row['top_drivers'], width=30))}</td>"
            f"<td>{html.escape(_short_tokens(row['primary_risk'], limit=1, width=24))}</td>"
            f'<td><span class="{state_class}">{state}</span></td>'
            "</tr>"
        )
    return "".join(rows)


def build_daily_watch20_client_html(artifact: DailyWatch20Artifact) -> str:
    """Build a client-safe responsive HTML report."""

    frame = client_display_frame(artifact)
    industries = _group_share(frame, "industry", limit=6)
    themes = _group_share(frame, "theme", limit=6)
    regime = html.escape(_regime_summary(artifact.receipt))
    minute = html.escape(_client_minute_text(artifact.receipt))
    warning = _client_candidate_data_warning(artifact.receipt)
    warning_html = f'<p class="data-warning">{html.escape(warning)}</p>' if warning else ""
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日20只重点关注 {_date_dash(artifact.signal_date)}</title>
<style>
:root{{--bg:#f7f4ec;--wash:#edf0fa;--panel:rgba(255,255,255,.52);--line:#cdd0cf;--grid:rgba(205,208,207,.34);--text:#111820;--muted:#707985;--blue:#1557ff;--warn:#a86f00}}
*{{box-sizing:border-box}}
body{{margin:0;background-color:var(--bg);background-image:
linear-gradient(90deg,var(--grid) 1px,transparent 1px),
linear-gradient(var(--grid) 1px,transparent 1px),
linear-gradient(105deg,var(--bg),var(--wash));background-size:40px 40px,
40px 40px,100% 100%;color:var(--text);font:14px/1.55 Inter,
"Noto Sans CJK SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1180px;margin:auto;padding:34px 28px 30px}}
header{{padding-bottom:20px;border-bottom:1px solid var(--line)}}
.kicker{{color:var(--blue);font-weight:800;font-size:12px;letter-spacing:.04em}}
h1{{font:800 34px/1.2 "Source Han Serif SC","Noto Serif CJK SC","Songti SC",serif;margin:10px 0 7px}}
h2{{font-size:16px;margin:0 0 8px}}p{{margin:0}}.meta,.note{{color:var(--muted)}}
.status{{margin:16px 0 0;padding:13px 0 15px;border-bottom:1px solid var(--line)}}.status strong{{color:var(--text)}}.data-warning{{margin-top:8px;color:var(--warn)}}
.summary{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin:18px 0}}
.panel{{background:var(--panel);border-top:2px solid var(--blue);padding:14px 15px 15px}}
.distribution{{color:var(--muted);margin-top:5px}}
.table-wrap{{overflow-x:auto;border-top:2px solid var(--text);
background:rgba(255,255,255,.38)}}
table{{width:100%;border-collapse:collapse;min-width:940px}}
th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;
vertical-align:top}}
th{{color:var(--muted);font-size:12px;background:rgba(237,240,250,.62)}}
tbody tr:nth-child(even){{background:rgba(255,255,255,.28)}}
td small{{display:block;color:var(--muted)}}
.state-new{{color:var(--blue);font-weight:800}}
.state-kept{{color:var(--muted);font-weight:700}}
.disclaimer{{margin-top:18px;padding:14px 0 0;border-top:1px solid var(--line);
color:var(--warn);font-weight:700}}
@media(max-width:760px){{.wrap{{padding:20px 14px}}
.summary{{grid-template-columns:1fr;gap:12px}}h1{{font-size:27px}}}}
</style></head><body><main class="wrap">
<header><p class="kicker">{_date_dash(artifact.signal_date)} · DAILYWATCH20 / DAILY FOCUS</p>
<h1>今日20只重点关注</h1>
<p class="meta">DailyWatch20 研究版 · 源数据 {_date_dash(artifact.source_date)} · 收盘后生成，非实时</p></header>
<section class="status"><strong>市场状态：{regime}</strong><p>{minute}</p>
{warning_html}<p class="note">{CLIENT_METHOD_SUMMARY}；清单按行业与代码整理，序号不代表推荐优先级。</p></section>
<section class="summary">
<div class="panel"><h2>行业分布</h2><p class="distribution">
{html.escape(_share_text(industries))}</p></div>
<div class="panel"><h2>主题分布</h2><p class="distribution">
{html.escape(_share_text(themes))}</p></div></section>
<section class="table-wrap"><table><thead><tr>
<th>序号</th><th>股票</th><th>行业</th><th>主题</th>
<th>关注理由</th><th>主要风险</th><th>状态</th></tr></thead>
<tbody>{_client_html_rows(frame)}</tbody></table></section>
<footer class="disclaimer">{CLIENT_DISCLAIMER} 模型结果基于历史数据与收盘后可得信息，
不能替代公告核验、价格判断和盘中确认。</footer>
</main></body></html>"""
    return validate_daily_watch20_client_copy(document)


def render_daily_watch20_client_markdown(
    artifact: DailyWatch20Artifact,
    *,
    strategy_doc_url: str | None = None,
) -> str:
    """Render the client Feishu text without internal construction details."""

    frame = client_display_frame(artifact)
    industries = _group_share(frame, "industry", limit=3)
    themes = _group_share(frame, "theme", limit=3)
    warning = _client_candidate_data_warning(artifact.receipt)
    lines = [
        f"# 今日20只重点关注（{_date_dash(artifact.signal_date)}）",
        "",
        f"DailyWatch20 研究版 · 源数据 {_date_dash(artifact.source_date)} · 收盘后生成，非实时",
        f"{CLIENT_METHOD_SUMMARY}。以下按行业与代码排列，序号不代表推荐优先级。",
        "",
    ]
    if warning:
        lines.extend([warning, ""])
    for row in _records(frame):
        lines.append(
            f"{int(row['display_no'])}. {row['symbol']} {row['name']}｜"
            f"{row['industry'] or '未分类'}｜{row['theme'] or '未分类'}｜"
            f"关注：{_short_tokens(row['top_drivers'], width=28)}｜"
            f"风险：{_short_tokens(row['primary_risk'], limit=1, width=22)}"
        )
    lines.extend(
        [
            "",
            "## 结构摘要",
            "- 行业分布：" + _share_text(industries, limit=3),
            "- 主题分布：" + _share_text(themes, limit=3),
            "- 市场状态：" + _regime_summary(artifact.receipt),
            "- 数据状态：" + _client_minute_text(artifact.receipt),
        ]
    )
    if strategy_doc_url:
        lines.extend(["", f"查看完整方法：[每日关注清单方法说明]({strategy_doc_url})"])
    lines.extend(["", CLIENT_DISCLAIMER])
    return validate_daily_watch20_client_copy("\n".join(lines).rstrip() + "\n")


def _draw_client_stock_table(ax: Any, frame: pd.DataFrame, *, font: Any) -> None:
    ax.axis("off")
    name_width = _client_table_display_budget(1)
    classification_width = _client_table_display_budget(2)
    cell_rows: list[list[str]] = []
    for row in _records(frame):
        cell_rows.append(
            [
                str(int(row["display_no"])),
                f"{_truncate_display(row['name'], name_width)}\n{row['symbol']}",
                f"{_truncate_display(row['industry'], classification_width)}\n"
                f"{_truncate_display(row['theme'], classification_width)}",
                _png_reason_risk_text(row["top_drivers"], row["primary_risk"]),
            ]
        )
    table = ax.table(
        cellText=cell_rows,
        colLabels=["序号", "股票", "行业 / 主题", "关注理由 / 风险"],
        cellLoc="left",
        colLoc="left",
        colWidths=_CLIENT_TABLE_COLUMN_WIDTHS,
        bbox=(0, 0, 1, 1),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.1)
    for (row_index, column), cell in table.get_celld().items():
        cell.set_edgecolor("#2a313b")
        cell.set_linewidth(0.55)
        cell.set_facecolor(
            "#11161d" if row_index == 0 else ("#151b23" if row_index % 2 else "#121820")
        )
        cell.get_text().set_color("#94a0af" if row_index == 0 else "#edf2f7")
        cell.get_text().set_verticalalignment("center")
        if font is not None:
            cell.get_text().set_fontproperties(font)
        cell.get_text().set_fontsize(6.5 if column == 3 else 7.1)
        cell.get_text().set_linespacing(1.0)


def _draw_client_header(
    fig: Any,
    artifact: DailyWatch20Artifact,
    *,
    font: Any,
) -> None:
    fig.text(
        0.05,
        0.965,
        f"今日20只重点关注 · {_date_dash(artifact.signal_date)}",
        color="#edf2f7",
        fontsize=20,
        fontweight="bold",
        fontproperties=font,
        va="top",
    )
    fig.text(
        0.05,
        0.932,
        f"DailyWatch20 研究版 · 源数据 {_date_dash(artifact.source_date)} · 收盘后生成，非实时",
        color="#94a0af",
        fontsize=8.5,
        fontproperties=font,
        va="top",
    )
    fig.text(
        0.05,
        0.895,
        "市场状态",
        color="#20c997",
        fontsize=9,
        fontproperties=font,
        va="top",
    )
    fig.text(
        0.05,
        0.873,
        _truncate(_regime_summary(artifact.receipt), 54),
        color="#ffd43b",
        fontsize=11,
        fontweight="bold",
        fontproperties=font,
        va="top",
    )
    fig.text(
        0.95,
        0.695,
        "按行业与代码整理 · 序号不代表推荐优先级",
        color="#94a0af",
        fontsize=7.5,
        fontproperties=font,
        ha="right",
        va="top",
    )


def _draw_share_bars(
    ax: Any,
    shares: pd.Series,
    *,
    title: str,
    colors: tuple[str, ...],
    font: Any,
) -> None:
    ordered = shares.sort_values(ascending=True)
    positions = range(len(ordered))
    maximum = float(ordered.max()) if not ordered.empty else 1.0
    ax.barh(
        positions,
        ordered.values,
        color=colors[: len(ordered)],
        height=0.55,
    )
    ax.set_xlim(0, max(maximum * 1.32, 0.1))
    ax.set_xticks([])
    ax.set_yticks(
        list(positions),
        labels=[_truncate(label, 8) for label in ordered.index],
    )
    ax.tick_params(axis="y", length=0, colors="#d7dee8", labelsize=6.7, pad=4)
    ax.set_title(title, loc="left", color="#94a0af", fontsize=8, fontproperties=font, pad=4)
    for position, value in enumerate(ordered.values):
        ax.text(
            float(value) + maximum * 0.025,
            position,
            f"{float(value):.0%}",
            color="#d7dee8",
            fontsize=6.7,
            va="center",
            fontproperties=font,
        )
    for label in ax.get_yticklabels():
        if font is not None:
            label.set_fontproperties(font)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _draw_client_footer(
    fig: Any,
    artifact: DailyWatch20Artifact,
    *,
    font: Any,
) -> None:
    warning = _client_candidate_data_warning(artifact.receipt)
    if warning:
        warning_lines = _wrap_display_text(warning, width=72, max_lines=2)
        fig.text(
            0.05,
            0.095,
            "\n".join(warning_lines),
            color="#ffe58f",
            fontsize=7.1,
            fontproperties=font,
            va="top",
        )
    fig.text(
        0.05,
        0.059 if warning else 0.073,
        f"模型方法：{CLIENT_METHOD_SUMMARY}\n日频与分钟输入须通过 freshness 门禁。",
        color="#94a0af",
        fontsize=7.3,
        fontproperties=font,
        va="top",
    )
    fig.text(
        0.05,
        0.015 if warning else 0.025,
        CLIENT_DISCLAIMER,
        color="#ffe58f",
        fontsize=8.2,
        fontweight="bold",
        fontproperties=font,
        va="top",
    )


def generate_daily_watch20_client_png(
    artifact: DailyWatch20Artifact,
    output_path: str | Path,
) -> Path:
    """Generate a compact 1280x1600 client sheet for mobile Feishu viewing."""

    import matplotlib.pyplot as plt

    from a_share_daily.charts.theme import cjk

    frame = client_display_frame(artifact)
    _validate_client_frame_copy(artifact, frame)
    industries = _group_share(frame, "industry", limit=5)
    themes = _group_share(frame, "theme", limit=5)
    fig = plt.figure(figsize=(8, 10), facecolor="#0d1117")
    ax_industry = fig.add_axes((0.105, 0.72, 0.36, 0.115), facecolor="#151b23")
    ax_theme = fig.add_axes((0.585, 0.72, 0.365, 0.115), facecolor="#151b23")
    ax_left = fig.add_axes((0.045, 0.10, 0.44, 0.575), facecolor="#151b23")
    ax_right = fig.add_axes((0.515, 0.10, 0.44, 0.575), facecolor="#151b23")
    _draw_client_header(fig, artifact, font=cjk)
    _draw_share_bars(
        ax_industry,
        industries,
        title="行业分布",
        colors=("#20c997", "#63e6be", "#6bc5ff", "#748ffc", "#a9e34b", "#f783ac"),
        font=cjk,
    )
    _draw_share_bars(
        ax_theme,
        themes,
        title="主题分布",
        colors=("#ffd43b", "#ff922b", "#f783ac", "#cc5de8", "#6bc5ff", "#20c997"),
        font=cjk,
    )
    _draw_client_stock_table(ax_left, frame.iloc[:10], font=cjk)
    _draw_client_stock_table(ax_right, frame.iloc[10:], font=cjk)
    _draw_client_footer(fig, artifact, font=cjk)
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.stem}.tmp{output.suffix}")
    try:
        fig.savefig(tmp, dpi=160, facecolor="#0d1117", edgecolor="none")
        tmp.replace(output)
    finally:
        plt.close(fig)
        tmp.unlink(missing_ok=True)
    return output


__all__ = [
    "CLIENT_DISCLAIMER",
    "CLIENT_METHOD_FACTORS",
    "CLIENT_METHOD_SUMMARY",
    "_client_candidate_data_warning",
    "build_daily_watch20_client_html",
    "client_display_frame",
    "generate_daily_watch20_client_png",
    "render_daily_watch20_client_markdown",
    "validate_daily_watch20_client_copy",
]
