"""Renderers for the A-share evening review markdown / JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd

from .. import data as D
from ..market_temperature_render import render_market_temperature_section
from .formatters import _fmt_yuan, _pct, _sign
from .loaders import build_review_payload


def _render_title(trade_date: str) -> list[str]:
    """盘后点评标题行（含星期）。"""
    dt = datetime.strptime(trade_date, "%Y%m%d")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
    return [f"## {trade_date} {weekday} 盘后点评", ""]


def _render_indices_section(indices: Mapping[str, Any]) -> list[str]:
    """二、指数总览。"""
    lines = ["### 二、指数总览", ""]
    if indices:
        for _code, info in indices.items():
            tag = "[OK]" if info["pct_chg"] >= 0 else "[WARN]"
            lines.append(
                f"{info['name']}: {info['close']:.2f} {tag} {_pct(info['pct_chg'])} | "
                f"成交 {_fmt_yuan(info['amount'] * 1000)}"
            )
        lines.append("")
    else:
        lines.append("指数数据暂缺")
        lines.append("")
    return lines


def _render_overview_section(overview: Mapping[str, Any]) -> list[str]:
    """三、市场总览（中位数/加权/涨跌家数/VWAP/分布）。"""
    lines = ["### 三、市场总览", ""]
    median = overview.get("median_pct_chg", 0)
    wavg = overview.get("wavg_pct_chg", 0)
    tag_mkt = "[OK]" if median > 0 else "[WARN]"
    turnover = overview.get("turnover_total", 0) * 1000
    b = overview.get("breadth", {})

    lines.append(
        f"全市场中位数涨跌 {tag_mkt} {_pct(median)} | "
        f"成交额加权涨跌 {_pct(wavg)} | "
        f"总成交 {_fmt_yuan(turnover)}"
    )
    if abs(wavg - median) > 0.5:
        direction = "高成交标的相对偏强" if wavg > median else "高成交标的相对偏弱"
        lines.append(f"> 成交额加权与中位数偏离 {abs(wavg - median):.1f}pp，{direction}")
    lines.append("")

    lines.append(
        f"上涨 {b['up']} 家 | 下跌 {b['down']} 家 | 平盘 {b['flat']} 家 | "
        f"上涨率 {b.get('up_ratio', 0)}%"
    )
    lines.append("")

    vwap_r = overview.get("vwap_above_ratio", 0)
    intra = overview.get("intraday", {})
    lines.append(
        f"站上 VWAP 比例: {vwap_r}% | "
        f"开盘跳空: {intra.get('gap_open_pct', 0):+.2f}% | "
        f"日内振幅中位数: {intra.get('median_day_range_pct', 0):.2f}% | "
        f"收盘位置: {intra.get('median_close_position_pct', 0):.1f}%"
    )
    lines.append("")

    dist = overview.get("distribution", {})
    if dist:
        items = "  ".join(f"{k}:{v}" for k, v in dist.items())
        lines.append(f"涨跌分布: {items}")
        lines.append("")
    return lines


def _render_limit_section(limit: Mapping[str, Any], overview: Mapping[str, Any]) -> list[str]:
    """四、涨跌停。"""
    lines = ["### 四、涨跌停", ""]
    lu = limit.get("limit_up", {})
    limit_down = limit.get("limit_down", {})
    dl = limit_down.get("count", overview.get("down_limit_count", 0))
    exact_limits = limit_down.get("method") == "exchange_limit_price"
    down_label = "跌停" if exact_limits else "跌停（近似）"
    up5 = overview.get("up5_count", 0)
    down5 = overview.get("down5_count", 0)
    lines.append(
        f"涨停 {lu.get('count') if lu.get('count') is not None else 'N/A'} 家 | "
        f"{down_label} {dl} 家 | "
        f"涨幅>5% {up5} 家 | "
        f"跌幅>5% {down5} 家"
    )
    if limit.get("max_board", 0) > 0:
        lines.append(f"> 最高连板: {limit['max_board']} 板")
    lines.append("")
    if limit.get("limit_up_names"):
        lines.append(f"涨停代表: {'、'.join(limit['limit_up_names'][:12])}")
        lines.append("")
    return lines


def _render_flow_section(flow: Mapping[str, Any]) -> list[str]:
    """五、资金动向（北向/大单/活跃买入）。"""
    lines = ["### 五、资金动向", ""]
    nb = flow.get("northbound", {})
    if nb:
        lines.append(
            f"北向净流入 {_sign(nb.get('north_net', 0))} | "
            f"沪股通 {_sign(nb.get('hgt', 0))} | "
            f"深股通 {_sign(nb.get('sgt', 0))}"
        )
        lines.append("")
    mf = flow.get("moneyflow", {})
    if mf:
        net = mf.get("net_total", 0)
        tag_mf = "[OK]" if net > 0 else "[WARN]"
        lines.append(
            f"大单资金代理 {tag_mf} {_sign(net)} | "
            f"净流入 {mf.get('inflow_stocks', 0)} 家 / "
            f"净流出 {mf.get('outflow_stocks', 0)} 家"
        )
        lines.append("")
    active = flow.get("north_active_buy", [])
    if active:
        items = ", ".join(f"{a['name']}({_pct(a['change'])})" for a in active)
        lines.append(f"北向活跃买入: {items}")
        lines.append("")
    return lines


def _render_margin_section(margin: Mapping[str, Any]) -> list[str]:
    """六、融资融券。"""
    lines = ["### 六、融资融券", ""]
    if margin:
        lines.append(
            f"融资余额 {_fmt_yuan(margin.get('financing_balance', 0))} | "
            f"融券余额 {_fmt_yuan(margin.get('short_balance', 0))} | "
            f"两融总额 {_fmt_yuan(margin.get('margin_balance', 0))}"
        )
    else:
        lines.append("两融数据暂缺（T+1延迟）")
    lines.append("")
    return lines


def _render_industry_section(industry: pd.DataFrame) -> list[str]:
    """七、行业板块 TOP10 与跌幅靠前。"""
    lines = ["### 七、行业板块 TOP10", ""]
    if not industry.empty:
        lines.append("| 行业 | 均涨跌 | 中位数 | 家数 | 上涨率 |")
        lines.append("|------|--------|--------|------|--------|")
        for _, row in industry.head(10).iterrows():
            lines.append(
                f"| {row['industry']} | {_pct(row['avg_pct_chg'])} | "
                f"{_pct(row['median_pct_chg'])} | {int(row['stock_count'])} | "
                f"{row['up_ratio']}% |"
            )
        lines.append("")
        bottom = industry.tail(5).iloc[::-1]
        lines.append("跌幅靠前行业:")
        items = "、".join(
            f"{r['industry']}({_pct(r['avg_pct_chg'])})" for _, r in bottom.iterrows()
        )
        lines.append(f"{items}")
        lines.append("")
    return lines


def _render_top_amount_section(top_amt: pd.DataFrame) -> list[str]:
    """八、高成交核心票 TOP10。"""
    lines = ["### 八、高成交核心票 TOP10", ""]
    if not top_amt.empty:
        lines.append("| 代码 | 成交额(亿) | 涨跌 |")
        lines.append("|------|-----------|------|")
        for _, r in top_amt.head(10).iterrows():
            lines.append(f"| {r['ts_code'][:6]} | {r['amount_yi']:.1f} | {_pct(r['pct_chg'])} |")
        lines.append("")
    return lines


def _render_hot_sectors_section(sectors: Mapping[str, Any]) -> list[str]:
    """九、热门概念 TOP5。"""
    lines = ["### 九、热门概念 TOP5", ""]
    top_c = sectors.get("top_by_change", [])[:5]
    if top_c:
        lines.append("| 概念 | 涨幅 | 龙头 | 涨停数 |")
        lines.append("|------|------|------|--------|")
        for c in top_c:
            lines.append(
                f"| {c['name']} | {_pct(c.get('pct_change', 0))} | "
                f"{c.get('lead_stock', '-')}({_pct(c.get('lead_stock_pct_change', 0))}) | "
                f"{int(c.get('z_t_num', 0))} |"
            )
        lines.append("")
    return lines


def _render_extreme_section(overview: Mapping[str, Any]) -> list[str]:
    """十、极端异动（涨幅/跌幅前五）。"""
    lines = ["### 十、极端异动", ""]
    top_up = overview.get("top_gainers", [])[:5]
    top_down = overview.get("top_losers", [])[:5]
    if top_up:
        items = "、".join(f"{r['ts_code']}({_pct(r['pct_chg'])})" for r in top_up)
        lines.append(f"涨幅前五: {items}")
        lines.append("")
    if top_down:
        items = "、".join(f"{r['ts_code']}({_pct(r['pct_chg'])})" for r in top_down)
        lines.append(f"跌幅前五: {items}")
        lines.append("")
    return lines


def build_report(trade_date: str) -> str:
    """Build complete markdown report."""
    payload = build_review_payload(trade_date)
    indices = payload["indices"]
    overview = payload["overview"]
    limit = payload["limits"]
    flow = payload["moneyflow"]
    margin = payload["margin"]
    sectors = payload["hot_sectors"]
    industry = pd.DataFrame(payload["industry_stats"])
    top_amt = pd.DataFrame(payload["top_amount_stocks"])

    lines: list[str] = []
    lines.extend(_render_title(trade_date))
    lines.extend(
        render_market_temperature_section(
            payload.get("market_temperature", {}),
            heading="一、市场状态",
        )
    )
    lines.append("")
    lines.extend(_render_indices_section(indices))
    lines.extend(_render_overview_section(overview))
    lines.extend(_render_limit_section(limit, overview))
    lines.extend(_render_flow_section(flow))
    lines.extend(_render_margin_section(margin))
    lines.extend(_render_industry_section(industry))
    lines.extend(_render_top_amount_section(top_amt))
    lines.extend(_render_hot_sectors_section(sectors))
    lines.extend(_render_extreme_section(overview))

    lines.append("---")
    lines.append(
        f"*数据: Tushare / market-data-platform | 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}*"
    )

    return "\n".join(lines)


def build_json(trade_date: str) -> str:
    """Build JSON report."""
    return json.dumps(build_review_payload(trade_date), ensure_ascii=False, indent=2, default=str)


# ── CLI entry (for standalone use) ───────────────────────────


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="盘后点评")
    parser.add_argument("--date", help="Trade date YYYYMMDD (default: latest available)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    if args.date:
        trade_date = args.date
    else:
        trade_date = D._latest_date("daily")
        if not trade_date:
            print("[FAIL] 无法确定最新交易日，请用 --date 指定", file=sys.stderr)
            return 1

    if args.json:
        print(build_json(trade_date))
    else:
        print(build_report(trade_date))
    return 0
