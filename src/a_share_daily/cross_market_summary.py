"""Markdown rendering helpers for cross-market snapshots."""

from __future__ import annotations

from typing import Any


def _src_note(source: str) -> str:
    """Render the data-source annotation for macro/CBOE rows."""
    if source == "fred":
        return "（FRED）"
    if source == "cboe_history":
        return "（Cboe）"
    return ""


def _render_global_lead_lag_section(data: dict[str, Any]) -> list[str]:
    """全球领先资产 → A 股概念映射段。"""
    mapping = data.get("global_lead_lag") or data.get("concept_mapping", [])
    if not mapping:
        return []
    lines = ["### 全球领先资产映射"]
    significant = [m for m in mapping if abs(m.get("avg_pct_chg", 0)) > 1]
    if significant:
        for m in significant[:6]:
            avg = m["avg_pct_chg"]
            signal = m["signal"]
            tag = "[OK]" if signal == "bullish" else "[WARN]"
            drivers = ", ".join(m.get("drivers", [])[:3])
            markets = "/".join(m.get("markets", []))
            suffix = f" [{markets}]" if markets else ""
            lines.append(f"- {tag} {m['concept']}（{avg:+.1f}%）{suffix}，驱动 {drivers}")
    else:
        lines.append("- 全球领先资产波动均<1%，无明显映射信号")
    lines.append("")
    return lines


def _render_korea_signal_section(data: dict[str, Any]) -> list[str]:
    """Render Korea's lead signal without hiding daily-proxy limitations."""
    signal = data.get("korea_preopen")
    if not isinstance(signal, dict) or not signal or signal.get("source") == "unavailable":
        return []
    tag = (
        "[OK]"
        if signal.get("signal") == "bullish"
        else "[WARN]"
        if signal.get("signal") == "bearish"
        else ""
    )
    concepts = "、".join(str(item) for item in signal.get("concepts", [])[:5]) or "韩国核心资产"
    source_note = (
        "日线代理，非盘中数据"
        if signal.get("source") == "daily-proxy"
        else str(signal.get("source"))
    )
    return [
        "### 韩国早盘 → A股开盘信号",
        f"- {tag} {signal.get('signal', 'neutral')}，行业残差 {float(signal.get('residual_pct_chg', 0)):+.1f}%，"
        f"映射 {concepts}；数据源：{source_note}",
        "",
    ]


def _render_korea_overnight_section(data: dict[str, Any]) -> list[str]:
    """Render Korea's next-session warning proxy when available."""
    signal = data.get("korea_overnight")
    if not isinstance(signal, dict) or not signal or signal.get("source") == "unavailable":
        return []
    level = signal.get("risk_level", "unknown")
    drivers = "、".join(str(item) for item in signal.get("drivers", [])[:3])
    source_note = "日线代理" if signal.get("source") == "daily-proxy" else str(signal.get("source"))
    return [
        "### 韩国盘后/夜盘 → 次日A股预警",
        f"- 风险等级：{level}，方向：{signal.get('signal', 'neutral')}，驱动：{drivers or '暂无'}；数据源：{source_note}",
        "",
    ]


def _render_commodity_section(data: dict[str, Any]) -> list[str]:
    """商品 → A 股概念映射段。"""
    comm_map = data.get("commodity_concept_mapping", [])
    if not comm_map:
        return []
    lines = ["### 商品映射"]
    for m in comm_map[:4]:
        avg = m["avg_pct_chg"]
        signal = m["signal"]
        tag = "[OK]" if signal == "bullish" else "[WARN]" if signal == "bearish" else ""
        drivers = ", ".join(m.get("drivers", [])[:2])
        lines.append(f"- {tag} {m['concept']}（{avg:+.1f}%），驱动 {drivers}")
    lines.append("")
    return lines


def _render_macro_section(data: dict[str, Any]) -> list[str]:
    """宏观指标段（DX-Y.NYB / VIX / VVIX / TNX）。"""
    macros = data.get("macros", {})
    if not macros or "error" in macros:
        return []
    lines = ["### 宏观环境"]
    for sym in ["DX-Y.NYB", "^VIX", "^VVIX", "^TNX"]:
        m = macros.get(sym, {})
        if not m or "close" not in m:
            continue
        label = m.get("label", sym)
        val = m["close"]
        pct = m.get("pct_chg", 0)
        src = m.get("source", "")
        if sym == "^VIX":
            level = "恐慌" if val > 25 else "偏高" if val > 20 else "正常"
            tag = "[WARN]" if val > 25 else "[OK]"
            lines.append(f"- {tag} {label}: {val}（{pct:+.1f}%），{level}{_src_note(src)}")
        elif sym == "DX-Y.NYB":
            direction = "偏强" if val > 102 else "偏弱" if val < 99 else "中性"
            lines.append(f"- {label}: {val}（{pct:+.1f}%），{direction}")
        else:
            lines.append(f"- {label}: {val}（{pct:+.1f}%）{_src_note(src)}")
    lines.append("")
    return lines


def _render_aaii_section(data: dict[str, Any]) -> list[str]:
    """AAII 散户情绪段。"""
    aaii = data.get("aaii_sentiment")
    if not aaii or "bullish_pct" not in aaii:
        return []
    bull = aaii.get("bullish_pct", 0)
    bear = aaii.get("bearish_pct", 0)
    spread = bull - bear
    tag = "[OK]" if spread > 10 else "[WARN]" if spread < -10 else ""
    return [f"- AAII 散户情绪: 看多 {bull}% / 看空 {bear}% (多空差 {spread:+.0f}%) {tag}", ""]


def _render_cboe_section(data: dict[str, Any]) -> list[str]:
    """CBOE Put/Call 与 VIX 恐贪段。"""
    cboe = data.get("cboe_putcall")
    if not cboe:
        return []
    if "vix" in cboe:
        vix = cboe["vix"]
        level = "恐慌" if vix > 25 else "偏高" if vix > 20 else "正常"
        tag = "[WARN]" if vix > 25 else "[OK]"
        return [f"- VIX 恐贪指标（FRED）: {vix}，{level} {tag}"]
    if "equity_ratio" in cboe:
        eq = cboe.get("equity_ratio", 0)
        defensive = isinstance(eq, (int, float)) and eq > 0.8
        tag = "[WARN]" if defensive else "[OK]"
        note = " >0.8 偏防御" if defensive else ""
        return [f"- CBOE Put/Call 比率（equity）: {eq} {tag} {note}"]
    return []


def generate_summary(data: dict[str, Any]) -> str:
    """Generate a readable cross-market summary markdown block.

    Suitable for inclusion in pre-market or post-market reports.
    Only includes concepts where the external move is significant (>1%).
    """
    lines: list[str] = []
    lines.extend(_render_global_lead_lag_section(data))
    lines.extend(_render_korea_signal_section(data))
    lines.extend(_render_korea_overnight_section(data))
    lines.extend(_render_commodity_section(data))
    lines.extend(_render_macro_section(data))
    lines.extend(_render_aaii_section(data))
    lines.extend(_render_cboe_section(data))
    return "\n".join(lines)
