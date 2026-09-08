"""Weekly recap markdown text with factual, neutral Chinese prose."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _classify_trend(up_days: int, total_days: int) -> str:
    """Map up/down day counts to a neutral trend label."""
    if up_days >= total_days * 0.8:
        return "强势上涨"
    if up_days >= total_days * 0.6:
        return "震荡偏强"
    if up_days <= total_days * 0.2:
        return "单边下跌"
    if up_days <= total_days * 0.4:
        return "震荡偏弱"
    return "震荡分化"


def _render_flow_section(total_net_flow: float) -> list[str]:
    """主力资金净流入/流出描述段，输入与输出均为亿元。"""
    if total_net_flow > 0:
        flow_desc = f"全周主力资金净流入 {total_net_flow:.0f} 亿元"
    elif total_net_flow < 0:
        flow_desc = f"全周主力资金净流出 {abs(total_net_flow):.0f} 亿元"
    else:
        flow_desc = "全周主力资金基本持平"
    return [f"资金动向：{flow_desc}。"]


def _render_margin_section(week_margin: dict[str, float], dates: list[str]) -> list[str]:
    """融资余额变化段（需首尾两日均有数据）。"""
    if dates[0] not in week_margin or dates[-1] not in week_margin:
        return []
    m0 = week_margin[dates[0]]
    m1 = week_margin[dates[-1]]
    change = m1 - m0
    if change > 0:
        description = f"融资余额从 {m0:.0f} 亿元增至 {m1:.0f} 亿元，增加 {change:.0f} 亿元。"
    elif change < 0:
        description = f"融资余额从 {m0:.0f} 亿元降至 {m1:.0f} 亿元，减少 {abs(change):.0f} 亿元。"
    else:
        description = f"融资余额维持在 {m1:.0f} 亿元。"
    return [description, ""]


def _render_gold_section(week_gold: dict[str, float]) -> list[str]:
    """外盘黄金周度表现段。"""
    if not week_gold or len(week_gold) < 2:
        return []
    gold_dates = sorted(week_gold.keys())
    gold_start = week_gold[gold_dates[0]]
    gold_end = week_gold[gold_dates[-1]]
    gold_wtd = gold_end - gold_start
    gold_pct = (gold_end / gold_start - 1) * 100 if gold_start > 0 else 0
    if gold_wtd > 0:
        price_change = "升至"
        direction = "走强"
    elif gold_wtd < 0:
        price_change = "降至"
        direction = "走弱"
    else:
        price_change = "维持在"
        direction = "持平"
    lines = [
        "",
        f"外盘黄金：本周从 {gold_start:.0f} 美元{price_change} {gold_end:.0f} 美元，"
        f"周涨跌幅为 {gold_pct:+.1f}%，整体{direction}。",
    ]
    if abs(gold_pct) > 2:
        lines.append(
            f"黄金本周波动较大（{abs(gold_pct):.1f}%）。A 股贵金属板块下周开盘可能受到外盘影响。"
        )
    return lines


def _format_turnover(amount_billion: float) -> str:
    """Format A-share turnover in 亿元 or 万亿元 for quick reading."""
    if abs(amount_billion) >= 10_000:
        return f"{amount_billion / 10_000:.2f} 万亿元"
    return f"{amount_billion:.0f} 亿元"


def _format_trade_date(raw: str) -> str:
    """Turn YYYYMMDD into natural Chinese month-day copy."""
    return f"{int(raw[4:6])}月{int(raw[6:8])}日"


def generate_weekly_text(
    week_daily: dict[str, pd.DataFrame],
    week_limits: dict[str, int],
    week_moneyflow: dict[str, float],
    week_margin: dict[str, float],
    trade_date: str,
    week_gold: dict[str, float] | None = None,
) -> str:
    """Generate weekly recap markdown. Returns markdown string."""
    dates = sorted(week_daily.keys())

    if len(dates) < 2:
        return f"# 本周复盘\n\n仅 {len(dates)} 个交易日数据，不足以生成周度复盘。"

    daily_stats = []
    for ds in dates:
        df = week_daily[ds]
        up = int((df["pct_chg"] > 0).sum())
        down = int((df["pct_chg"] < 0).sum())
        avg = df["pct_chg"].mean()
        amt = df["amount"].sum() / 1e5
        up_ratio = up / len(df) * 100
        lu = week_limits.get(ds, 0)
        nf = week_moneyflow.get(ds, 0)
        daily_stats.append(
            {
                "date": ds,
                "up": up,
                "down": down,
                "up_ratio": up_ratio,
                "avg_pct": avg,
                "amount": amt,
                "limit_up": lu,
                "net_flow": nf,
            }
        )

    total_days = len(daily_stats)
    up_days = sum(1 for s in daily_stats if int(s["up"]) > int(s["down"]))
    avg_up_ratio = np.mean([s["up_ratio"] for s in daily_stats])
    avg_pct_all = np.mean([s["avg_pct"] for s in daily_stats])
    total_amt = sum(s["amount"] for s in daily_stats)
    avg_amt = total_amt / total_days
    total_limit_up = sum(s["limit_up"] for s in daily_stats)
    avg_limit_up = total_limit_up / total_days
    total_net_flow = sum(s["net_flow"] for s in daily_stats)

    trend = _classify_trend(up_days, total_days)
    lines = [
        f"## 本周复盘（{_format_trade_date(dates[0])}至{_format_trade_date(dates[-1])}）",
        "",
        f"盘面特征：{trend}。本周 {total_days} 个交易日，{up_days} 天上涨、{total_days - up_days} 天下跌。"
        f"日均上涨家数占比 {avg_up_ratio:.0f}%，个股平均涨幅 {avg_pct_all:+.2f}%。",
        "",
        f"成交情况：周总成交额 {_format_turnover(total_amt)}，日均 {_format_turnover(avg_amt)}。",
        "",
    ]

    lines.extend(_render_flow_section(total_net_flow))

    lines.extend(_render_margin_section(week_margin, dates))
    lines.append("")

    lines.append(f"涨停统计：全周涨停 {total_limit_up} 只，日均涨停 {avg_limit_up:.1f} 只。")
    if avg_limit_up >= 100:
        lines.append("涨停数量处于较高水平，短线情绪活跃。")
    elif avg_limit_up >= 50:
        lines.append("涨停数量处于中等水平。")
    else:
        lines.append("涨停数量偏低，短线资金参与度有限。")

    lines.extend(_render_gold_section(week_gold or {}))

    return "\n".join(lines)
