"""English-canonical presentation catalogs for deterministic daily reports.

Source statements, identifiers and unknown source labels are never translated.
"""

from __future__ import annotations

from ops_common.locale import normalize_locale

NEWS_MARKET_LABELS = {"cn": "A股", "jp": "日股", "kr": "韩股", "us": "美股"}
CATEGORY_LABELS = {
    "policy": "政策",
    "company": "公司",
    "macro": "宏观",
    "sector": "行业",
}

_MARKET_TEMPERATURE_DIMENSIONS = (
    ("liquidity", "流动性"),
    ("breadth", "广度"),
    ("profit_effect", "赚钱效应"),
    ("loss_risk", "亏钱风险"),
    ("trend_confirmation", "趋势确认"),
    ("rotation_quality", "轮动质量"),
)


MESSAGES: dict[str, dict[str, str]] = {
    "freshness.section.title": {"en-US": "Data quality", "zh-CN": "数据质量"},
    "warning.source": {"en-US": "- [WARN] {warning}.", "zh-CN": "- [WARN] {warning}。"},
    "macro.row": {
        "en-US": "- {tag} {label}: {close} ({change}){asof}.",
        "zh-CN": "- {tag} {label}: {close} ({change}){asof}。",
    },
    "report.source_language": {
        "en-US": "Source content is retained in its original language.",
        "zh-CN": "来源内容保留原文。",
    },
    "quote": {
        "en-US": "{name} {symbol} {change}, close {close}",
        "zh-CN": "{name} {symbol} {change}，收 {close}",
    },
    "morning.news.title": {"en-US": "## 1. Overnight headlines", "zh-CN": "## 1. 隔夜要闻"},
    "news.category": {"en-US": "News", "zh-CN": "新闻"},
    "morning.news.missing": {
        "en-US": "- [WARN] No validated structured news items; free-form news is omitted.",
        "zh-CN": "- [WARN] 未取得通过结构化校验的新闻条目；跳过自由文本新闻。",
    },
    "morning.us.title": {"en-US": "## 2. U.S. overnight review", "zh-CN": "## 2. 美股隔夜回顾"},
    "morning.us.missing": {
        "en-US": "- [WARN] Missing SPY/QQQ/SMH benchmark quotes.",
        "zh-CN": "- [WARN] 缺少 SPY/QQQ/SMH 基准行情。",
    },
    "leaders": {"en-US": "- Leaders: ", "zh-CN": "- 领涨: "},
    "laggards": {"en-US": "- Laggards: ", "zh-CN": "- 领跌: "},
    "semiconductor.strong": {"en-US": "semiconductors outperform", "zh-CN": "半导体相对强"},
    "semiconductor.weak": {"en-US": "semiconductors underperform", "zh-CN": "半导体相对弱"},
    "morning.us.spread": {
        "en-US": "- Key divergence: SMH versus QQQ {spread}pp, {direction}.",
        "zh-CN": "- 关键矛盾: SMH 相对 QQQ {spread}pp，{direction}。",
    },
    "morning.asia.title": {"en-US": "## 3. Asia market snapshot", "zh-CN": "## 3. 亚洲市场速览"},
    "morning.asia.missing": {
        "en-US": "- [WARN] Missing Nikkei/KOSPI index snapshots.",
        "zh-CN": "- [WARN] 缺少日经/KOSPI 指数快照。",
    },
    "japan.semiconductors": {"en-US": "- Japan semiconductors: ", "zh-CN": "- 日本半导体: "},
    "korea.semiconductors": {"en-US": "- Korea semiconductors: ", "zh-CN": "- 韩国半导体: "},
    "korea.assets": {"en-US": "Korean core assets", "zh-CN": "韩国核心资产"},
    "daily.proxy": {"en-US": "daily proxy", "zh-CN": "日线代理"},
    "unavailable": {"en-US": "unavailable", "zh-CN": "暂无"},
    "korea.preopen.alert": {
        "en-US": "- {tag} Korea early session → A-share open: {signal}, industry "
        "residual {residual}%, mapping {concepts}, source {source}.",
        "zh-CN": "- {tag} 韩国早盘 → A股开盘: {signal}，行业残差 {residual}%，映射 "
        "{concepts}，数据源 {source}。",
    },
    "korea.preopen": {
        "en-US": "- {tag} Korea early session: {signal}, industry residual {residual}%, "
        "source {source}.",
        "zh-CN": "- {tag} 韩国早盘：{signal}，行业残差 {residual}%，数据源 {source}。",
    },
    "korea.overnight.alert": {
        "en-US": "- {tag} Korea after-hours/overnight → next A-share session: "
        "risk {level}, direction {signal}, drivers {drivers}, source "
        "{source}.",
        "zh-CN": "- {tag} 韩国盘后/夜盘 → 次日A股预警: 风险等级 {level}，方向 {signal}，驱动 "
        "{drivers}，数据源 {source}。",
    },
    "korea.overnight": {
        "en-US": "- {tag} Korea after-hours/overnight: risk {level}, direction "
        "{signal}, source {source}.",
        "zh-CN": "- {tag} 韩国盘后/夜盘：风险等级 {level}，方向 {signal}，数据源 {source}。",
    },
    "morning.mapping.title": {
        "en-US": "## 4. Cross-market transmission",
        "zh-CN": "## 4. 跨市场传导信号",
    },
    "morning.mapping.missing": {
        "en-US": "- [fetch] Global leading-asset mappings are below 1%; no "
        "significant transmission.",
        "zh-CN": "- [fetch] 全球领先资产映射波动均低于 1%，无显著传导。",
    },
    "mapping.markets": {"en-US": ", markets {markets}", "zh-CN": "，市场 {markets}"},
    "morning.mapping.row": {
        "en-US": "- {tag} {concept}: {change}{suffix}, drivers {drivers}",
        "zh-CN": "- {tag} {concept}: {change}{suffix}，驱动 {drivers}",
    },
    "morning.commodity.row": {
        "en-US": "- [fetch] Commodity mapping {concept}: {change}, {drivers}",
        "zh-CN": "- [fetch] 商品映射 {concept}: {change}，{drivers}",
    },
    "morning.ashare.title": {
        "en-US": "## 5. A-share pre-open themes",
        "zh-CN": "## 5. A股盘前热点预判",
    },
    "morning.topics": {
        "en-US": "- [fetch] DailyWatch20: {count} themes from the official topic_summary artifact.",
        "zh-CN": "- [fetch] DailyWatch20 热点主题 {count} 个，来源正式 topic_summary artifact。",
    },
    "topics.unavailable": {
        "en-US": "topic_summary.json unavailable",
        "zh-CN": "topic_summary.json 不可用",
    },
    "morning.topics.missing": {
        "en-US": "- [WARN] DailyWatch20 themes unavailable ({reason}).",
        "zh-CN": "- [WARN] DailyWatch20 热点主题不可用（{reason}）。",
    },
    "morning.candidates": {
        "en-US": "- [fetch] Theme candidate pool: {count} securities from the "
        "quant-research owner artifact.",
        "zh-CN": "- [fetch] 热点候选池 {count} 只，来源 quant-research owner artifact。",
    },
    "candidates.empty": {
        "en-US": "hotsector produced zero candidates",
        "zh-CN": "hotsector 产出 0 只候选",
    },
    "morning.candidates.empty": {
        "en-US": "- [WARN] Theme candidate pool is empty ({reason}).",
        "zh-CN": "- [WARN] 热点候选池为空（{reason}）。",
    },
    "morning.manifest.missing": {
        "en-US": "- [WARN] Missing hot-sector manifest.",
        "zh-CN": "- [WARN] 未取得 hot-sector manifest。",
    },
    "mapping.watch": {"en-US": "- Watch mappings: ", "zh-CN": "- 关注映射: "},
    "mapping.risk": {"en-US": "- Risk mappings: ", "zh-CN": "- 风险映射: "},
    "morning.macro.title": {"en-US": "## 6. Macro environment", "zh-CN": "## 6. 宏观环境"},
    "lag.days": {"en-US": ", lag {days} days", "zh-CN": "，滞后 {days} 天"},
    "asof": {"en-US": ", as of {date}{lag}", "zh-CN": "，截至 {date}{lag}"},
    "morning.aaii": {
        "en-US": "- [fetch] AAII: bullish {bullish} / bearish {bearish}, bull-bear spread {spread}",
        "zh-CN": "- [fetch] AAII: 看多 {bullish} / 看空 {bearish}，多空差 {spread}",
    },
    "morning.macro.missing": {
        "en-US": "- [WARN] Macro snapshot missing.",
        "zh-CN": "- [WARN] 宏观快照缺失。",
    },
    "news.disabled": {"en-US": "AI news fetching is disabled.", "zh-CN": "AI 新闻抓取已关闭。"},
    "evening.news.title": {"en-US": "## 2. Today’s headlines", "zh-CN": "## 2. 今日要闻"},
    "evening.news.missing": {
        "en-US": "- [WARN] No structured news items with source/url/published_at.",
        "zh-CN": "- [WARN] 未取得含 source/url/published_at 的结构化新闻条目。",
    },
    "evening.asia.title": {
        "en-US": "## 3. Asia market close review",
        "zh-CN": "## 3. 亚洲市场盘后复盘",
    },
    "index.quote": {
        "en-US": "{name} {change}, close {close}",
        "zh-CN": "{name} {change}，收 {close}",
    },
    "index": {"en-US": "Index", "zh-CN": "指数"},
    "evening.overview": {
        "en-US": "- [fetch] A-share median {median}, weighted {weighted}, turnover "
        "{turnover}, advancing share {advancing}%.",
        "zh-CN": "- [fetch] A股中位数 {median}，加权 {weighted}，成交 {turnover}，上涨率 "
        "{advancing}%。",
    },
    "evening.breadth": {
        "en-US": "- [fetch] Advancing {up}, declining {down}, above VWAP {above_vwap}%.",
        "zh-CN": "- [fetch] 上涨 {up} 家，下跌 {down} 家，站上 VWAP 比例 {above_vwap}%。",
    },
    "limit.down": {"en-US": "Limit-down", "zh-CN": "跌停"},
    "limit.down.approx": {"en-US": "Limit-down (approximate)", "zh-CN": "跌停（近似）"},
    "evening.limits": {
        "en-US": "- [fetch] Limit-up {up}, {down_label} {down}, longest limit-up "
        "streak {streak} sessions.",
        "zh-CN": "- [fetch] 涨停 {up} 家，{down_label} {down} 家，最高连板 {streak} 板。",
    },
    "evening.northbound": {
        "en-US": "- [fetch] Northbound net inflow {amount}.",
        "zh-CN": "- [fetch] 北向净流入 {amount}。",
    },
    "evening.sectors": {
        "en-US": "- [fetch] Leading concepts: {sectors}.",
        "zh-CN": "- [fetch] 热门概念: {sectors}。",
    },
    "evening.temperature.title": {"en-US": "## 1. Market temperature", "zh-CN": "## 1. 市场温度"},
    "evening.temperature.missing": {
        "en-US": "- [WARN] Market temperature data is insufficient; "
        "section 3 retains the underlying facts.",
        "zh-CN": "- [WARN] 市场温度数据不足；第 3 节仍保留原始市场事实。",
    },
    "data.insufficient": {"en-US": "Insufficient data", "zh-CN": "数据不足"},
    "evening.temperature": {
        "en-US": "- [fetch] Status: {status}; heat {heat}/100, fragility {fragility}/100.",
        "zh-CN": "- [fetch] 状态: {status}；热度 {heat}/100，脆弱度 {fragility}/100。",
    },
    "temperature.dimensions": {"en-US": "- [fetch] Six dimensions: ", "zh-CN": "- [fetch] 六维: "},
    "temperature.tensions": {"en-US": "- [WARN] Core tensions: ", "zh-CN": "- [WARN] 核心矛盾: "},
    "temperature.scope": {
        "en-US": "- [fetch] Scope: market-state observation only; the scale does "
        "not map directly to positions.",
        "zh-CN": "- [fetch] 口径: 仅作市场状态观察，当前刻度不直接映射仓位。",
    },
    "evening.mapping.title": {
        "en-US": "## 4. Cross-market transmission",
        "zh-CN": "## 4. 跨市场传导",
    },
    "evening.mapping.missing": {
        "en-US": "- [fetch] Global leading-asset mappings are below 1% or "
        "missing; no strong transmission signal.",
        "zh-CN": "- [fetch] 全球领先资产映射波动低于 1% 或暂缺，未给出强传导信号。",
    },
    "evening.mapping.row": {
        "en-US": "- {tag} {concept}: {change}, drivers {drivers}.",
        "zh-CN": "- {tag} {concept}: {change}，驱动 {drivers}。",
    },
    "evening.commodity.row": {
        "en-US": "- [fetch] Commodity mapping {concept}: {change}, {drivers}.",
        "zh-CN": "- [fetch] 商品映射 {concept}: {change}，{drivers}。",
    },
    "evening.macro.title": {"en-US": "## 5. Macro environment", "zh-CN": "## 5. 宏观环境"},
    "evening.aaii": {
        "en-US": "- [fetch] AAII: bullish {bullish} / bearish {bearish}, bull-bear "
        "spread {spread}.",
        "zh-CN": "- [fetch] AAII: 看多 {bullish} / 看空 {bearish}，多空差 {spread}。",
    },
    "evening.macro.missing": {
        "en-US": "- [WARN] Macro snapshot unavailable.",
        "zh-CN": "- [WARN] 宏观快照暂缺。",
    },
    "evening.watch.title": {"en-US": "## 6. Next-session checks", "zh-CN": "## 6. 次日验证"},
    "evening.watch.row": {
        "en-US": "- [fetch] Next-session check: {description}{punctuation}",
        "zh-CN": "- [fetch] 次日验证: {description}{punctuation}",
    },
    "watch.recovery": {
        "en-US": "whether the risk-appetite recovery continues",
        "zh-CN": "风险偏好修复延续性",
    },
    "watch.weakness": {
        "en-US": "whether the spread of weakness narrows",
        "zh-CN": "弱势扩散是否收敛",
    },
    "evening.watch.structure": {
        "en-US": "- [fetch] A-share structure: watch {direction} and whether turnover holds up.",
        "zh-CN": "- [fetch] A股内部结构: 关注{direction}，以及成交额能否维持。",
    },
    "evening.watch.global": {
        "en-US": "- [fetch] Before the next open: review U.S. close, "
        "USD/Treasuries/VIX, and Japan/Korea semiconductor chains.",
        "zh-CN": "- [fetch] 次日开盘前复核: 美股收盘、美元/美债/VIX、日韩半导体链表现。",
    },
    "freshness.missing": {
        "en-US": "- [WARN] Missing structured data-freshness manifest.",
        "zh-CN": "- [WARN] 缺少结构化数据新鲜度 manifest。",
    },
    "freshness.counts": {
        "en-US": "- [fetch] Target trading date {date}; fresh {fresh}, "
        "expected_delay {expected_delay}, skipped {skipped}, stale/missing "
        "{issues}, optional_degraded {optional}.",
        "zh-CN": "- [fetch] 目标交易日 {date}；fresh {fresh} 项，expected_delay "
        "{expected_delay} 项，skipped {skipped} 项，stale/missing {issues} "
        "项，optional_degraded {optional} 项。",
    },
    "freshness.asia": {
        "en-US": "- [fetch] Asia news dates: ",
        "zh-CN": "- [fetch] 亚洲市场新闻口径: ",
    },
    "freshness.us": {
        "en-US": "- [fetch] U.S. news/pre-open date: {date} (previous available U.S. trading day).",
        "zh-CN": "- [fetch] 美股新闻/盘前口径: {date}（上一可用美股交易日）。",
    },
    "freshness.status": {"en-US": "status {status}", "zh-CN": "状态 {status}"},
    "freshness.issue": {
        "en-US": "- [WARN] {label}({dataset}) latest {latest}, target {expected}; "
        "still unavailable after {attempts}, {detail}.",
        "zh-CN": "- [WARN] {label}({dataset}) 最新 {latest}，目标 {expected}；{attempts} "
        "后仍未更新，{detail}。",
    },
    "freshness.optional.detail": {
        "en-US": "Optional enhanced data is not aligned",
        "zh-CN": "可选增强数据未对齐",
    },
    "freshness.optional": {
        "en-US": "- [fetch] Optional enhanced data {label}({dataset}) latest "
        "{latest}, target {expected}; {detail}. Report is degraded; "
        "delivery is not blocked.",
        "zh-CN": "- [fetch] 可选增强数据 {label}({dataset}) 最新 {latest}，目标 "
        "{expected}；{detail}，报告已降级，不阻断发送。",
    },
    "freshness.delay": {
        "en-US": "- [fetch] {label}({dataset}) latest {latest}; {detail}.",
        "zh-CN": "- [fetch] {label}({dataset}) 最新 {latest}；{detail}。",
    },
    "freshness.skipped.detail": {"en-US": "Skipped", "zh-CN": "已跳过"},
    "freshness.more": {"en-US": " and others", "zh-CN": " 等"},
    "freshness.skipped": {"en-US": "- [fetch] Skipped ", "zh-CN": "- [fetch] 已跳过 "},
    "freshness.aligned": {
        "en-US": "- [OK] All enabled sources match the target trading date or have "
        "usable flat data.",
        "zh-CN": "- [OK] 所有启用数据源均已对齐目标交易日或 flat 可用。",
    },
    "attempt.current": {"en-US": "current generation pipeline", "zh-CN": "当前生成流程"},
    "separator.list": {"en-US": ", ", "zh-CN": "，"},
    "separator.clause": {"en-US": "; ", "zh-CN": "；"},
    "separator.enumeration": {"en-US": ", ", "zh-CN": "、"},
    "separator.dimensions": {"en-US": " | ", "zh-CN": "｜"},
    "punctuation.stop": {"en-US": ".", "zh-CN": "。"},
    "punctuation.colon": {"en-US": ": ", "zh-CN": "："},
    "report.method": {
        "en-US": "Structured market-intel facts + rule templates; no free-form writing.",
        "zh-CN": "market-intel 结构化事实 + 规则模板；未使用自由写作流程。",
    },
    "report.generated": {"en-US": "Generated at", "zh-CN": "生成时间"},
    "report.theme": {"en-US": "Report theme", "zh-CN": "报告主题"},
    "report.method.label": {"en-US": "Generation method", "zh-CN": "生成方式"},
    "morning.title": {
        "en-US": "# Asia pre-open / U.S. post-close ({date})",
        "zh-CN": "# 亚洲市场盘前 / 美股市场盘后（{date}）",
    },
    "evening.title": {
        "en-US": "# Asia market close review ({date})",
        "zh-CN": "# 亚洲市场收盘复盘（{date}）",
    },
    "freshness.title": {"en-US": "7. Data quality", "zh-CN": "7. 数据质量"},
    "news.item": {
        "en-US": "- [fetch] {market} | {category}: {summary} ({date}{source}: [{title}]({url}))",
        "zh-CN": "- [fetch] {market}｜{category}: {summary}（{date}{source}: [{title}]({url})）",
    },
    "freshness.skipped.item": {
        "en-US": "{label}({dataset}): {detail}",
        "zh-CN": "{label}({dataset})：{detail}",
    },
    "currency.trillion": {"en-US": "{value}tn CNY", "zh-CN": "{value}万亿"},
    "currency.hundred_million": {"en-US": "{value} × 100m CNY", "zh-CN": "{value}亿"},
    "currency.ten_thousand": {"en-US": "{value} × 10k CNY", "zh-CN": "{value}万"},
    "currency.yuan": {"en-US": "{value} CNY", "zh-CN": "{value}"},
}


KNOWN_LABELS: dict[str, str] = {
    "A股": "A-shares",
    "VIX 恐慌指数": "VIX volatility index",
    "DXY 美元指数": "DXY U.S. dollar index",
    "日股": "Japan",
    "韩股": "Korea",
    "美股": "U.S.",
    "政策": "Policy",
    "公司": "Company",
    "宏观": "Macro",
    "行业": "Sector",
    "标普500 ETF": "S&P 500 ETF",
    "纳斯达克100 ETF": "Nasdaq 100 ETF",
    "费城半导体 ETF": "Semiconductor ETF",
    "恒生指数": "Hang Seng Index",
    "日经225": "Nikkei 225",
    "韩国KOSPI": "KOSPI",
    "研究编辑部": "Research editorial",
    "暖白简报": "Warm light briefing",
    "深色终端": "Dark terminal",
    "流动性": "Liquidity",
    "广度": "Breadth",
    "赚钱效应": "Profitability",
    "亏钱风险": "Loss risk",
    "趋势确认": "Trend confirmation",
    "轮动质量": "Rotation quality",
    "数据不足": "Insufficient data",
    "升温但脆弱": "Warming but fragile",
    "偏热": "Hot",
    "结构活跃但脆弱": "Active structure but fragile",
    "温和活跃": "Moderately active",
    "结构分化且脆弱": "Divergent and fragile",
    "中性偏冷": "Neutral to cool",
    "偏冷且脆弱": "Cool and fragile",
    "偏冷": "Cool",
    "A股日线": "A-share daily prices",
    "A股基础指标": "A-share daily fundamentals",
    "复权因子": "Adjustment factors",
    "涨跌停状态": "Price-limit status",
    "沪深港通十大成交": "Stock Connect top ten turnover",
    "同花顺资金流": "THS money flow",
    "涨跌停明细": "Price-limit details",
    "东方财富概念": "Eastmoney concepts",
    "东方财富概念成分": "Eastmoney concept members",
    "开盘啦概念成分": "Kaipanla concept members",
    "同花顺热榜": "THS trending list",
    "开盘啦涨停池": "Kaipanla limit-up pool",
    "融资融券余额": "Margin balance",
    "融资融券明细": "Margin details",
    "指数日线": "Index daily prices",
    "同花顺行业成分": "THS industry members",
    "GitHub Actions 快照": "GitHub Actions snapshot",
    "本机定时补抓": "Local scheduled refresh",
    "Windows Task Scheduler 补抓": "Windows Task Scheduler refresh",
    "报告流水线最终补抓": "Final report-pipeline refresh",
    "手动生成": "Manual generation",
    "目标分区已落盘": "Target partition written",
    "参数 fallback 成功": "Parameter fallback succeeded",
    "接口正常返回但目标日期为空": "Provider returned no rows for the target date",
    "接口权限不足": "Provider permission denied",
    "请求超时或被冷却": "Request timed out or cooled down",
    "补抓命令异常退出": "Refresh command failed",
    "补抓结束但未生成目标分区": "Refresh completed without target partition",
    "高权限数据未启用": "Premium data not enabled",
    "已按配置暂时关闭": "Temporarily disabled by configuration",
    "未找到可用分区": "No usable partition found",
    "flat parquet，存在即视为可用": "Flat parquet is usable when present",
    "未指定目标交易日，仅检查可用性": "No target trading date; availability only",
    "已对齐目标交易日": "Aligned with target trading date",
    "补抓后仍旧": "Still stale after refresh",
    "未找到可用分区；可选增强数据降级": "No usable partition; optional enhanced data degraded",
    "补抓后仍旧；可选增强数据降级": "Still stale after refresh; optional enhanced data degraded",
    "沪深港通成交数据可能受官方披露节奏影响": "Stock Connect turnover may follow the official disclosure schedule",
    "融资融券数据允许 T+1/T+2 官方延迟": "Margin data allows official T+1/T+2 delay",
    "融资融券明细允许 T+1/T+2 官方延迟": "Margin details allow official T+1/T+2 delay",
}


def message(locale: str, key: str, **values: object) -> str:
    """Render catalog copy, falling back to English when a translation is absent."""
    translations = MESSAGES[key]
    template = translations.get(normalize_locale(locale), translations["en-US"])
    return template.format(**values)


def known_label(locale: str, value: object) -> str:
    """Localize known producer labels while preserving unknown source text."""
    text = str(value)
    return KNOWN_LABELS.get(text, text) if normalize_locale(locale) == "en-US" else text
