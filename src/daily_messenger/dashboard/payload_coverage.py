"""Coverage/source-analysis builders and large reference constants.

Depends on :mod:`payload_helpers`, :mod:`payload_state` and
:mod:`payload_aggregations`. Holds the data-source coverage report, the source
manifest/analysis, and the large reference tables (vendor specs, replication
report) that ``build_payload`` surfaces in the dashboard.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .payload_aggregations import _etl_source_rows
from .payload_helpers import (
    USD_CNY_ASSUMPTION,
    JsonDocument,
    PanelDocument,
    _as_list,
    _as_mapping,
    _number,
)
from .payload_state import _panel_is_derived

REFERENCE_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "alpha-vantage",
        "label": "Alpha Vantage",
        "title": "Alpha Vantage API",
        "url": "https://www.alphavantage.co/documentation/",
        "kind": "行情",
    },
    {
        "id": "fmp",
        "label": "FMP",
        "title": "Financial Modeling Prep API",
        "url": "https://site.financialmodelingprep.com/developer/docs",
        "kind": "行情/财务",
    },
    {
        "id": "twelve-data",
        "label": "Twelve Data",
        "title": "Twelve Data API",
        "url": "https://twelvedata.com/docs",
        "kind": "行情",
    },
    {
        "id": "eodhd",
        "label": "EODHD",
        "title": "EODHD Financial APIs",
        "url": "https://eodhd.com/pricing",
        "kind": "行情/成分/事件",
    },
    {
        "id": "tiingo",
        "label": "Tiingo",
        "title": "Tiingo Pricing",
        "url": "https://www.tiingo.com/pricing",
        "kind": "行情/基本面",
    },
    {
        "id": "massive",
        "label": "Massive",
        "title": "Massive Stock Market API",
        "url": "https://massive.com/pricing",
        "kind": "行情",
    },
    {
        "id": "cboe-daily",
        "label": "Cboe Daily",
        "title": "Cboe Daily Market Statistics",
        "url": "https://www.cboe.com/markets/us/options/market-statistics/daily/",
        "kind": "期权情绪",
    },
    {
        "id": "cboe-vix",
        "label": "Cboe VIX",
        "title": "Cboe VIX Historical Data",
        "url": "https://www.cboe.com/tradable-products/vix/vix-historical-data/",
        "kind": "波动率",
    },
    {
        "id": "fred-vix",
        "label": "FRED VIXCLS",
        "title": "FRED VIXCLS",
        "url": "https://fred.stlouisfed.org/series/VIXCLS",
        "kind": "宏观/波动率",
    },
    {
        "id": "aaii",
        "label": "AAII",
        "title": "AAII Investor Sentiment Survey",
        "url": "https://www.aaii.com/sentimentsurvey",
        "kind": "投资者情绪",
    },
    {
        "id": "sec-edgar",
        "label": "SEC EDGAR",
        "title": "SEC EDGAR APIs",
        "url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        "kind": "公司财报",
    },
    {
        "id": "coinbase",
        "label": "Coinbase",
        "title": "Coinbase Exchange API",
        "url": "https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductticker",
        "kind": "加密货币",
    },
    {
        "id": "okx",
        "label": "OKX",
        "title": "OKX API",
        "url": "https://www.okx.com/docs-v5/",
        "kind": "加密衍生品",
    },
    {
        "id": "sosovalue",
        "label": "SoSoValue",
        "title": "SoSoValue Open API",
        "url": "https://docs.sosovalue.com/",
        "kind": "BTC ETF",
    },
    {
        "id": "trading-economics",
        "label": "Trading Economics",
        "title": "Trading Economics Calendar API",
        "url": "https://tradingeconomics.com/api/calendar.aspx",
        "kind": "宏观日历",
    },
    {
        "id": "tushare",
        "label": "TuShare",
        "title": "TuShare",
        "url": "https://tushare.pro/",
        "kind": "A 股",
    },
    {
        "id": "factset",
        "label": "FactSet",
        "title": "FactSet Consensus Estimates",
        "url": "https://insight.factset.com/resources/factset-consensus-estimates-datafeed",
        "kind": "一致预期",
    },
    {
        "id": "bloomberg",
        "label": "Bloomberg",
        "title": "Bloomberg Data License",
        "url": "https://professional.bloomberg.com/products/data/data-management/data-license/",
        "kind": "机构数据",
    },
    {
        "id": "lseg",
        "label": "LSEG",
        "title": "LSEG Datastream",
        "url": "https://www.lseg.com/en/data-analytics/products/datastream-macroeconomic-analysis",
        "kind": "机构数据",
    },
    {
        "id": "sp-capital-iq",
        "label": "S&P Capital IQ",
        "title": "S&P Capital IQ Estimates",
        "url": "https://www.spglobal.com/market-intelligence/en/solutions/capital-iq-estimates",
        "kind": "一致预期",
    },
)

ETL_REFERENCE_IDS: dict[str, tuple[str, ...]] = {
    "market": ("alpha-vantage", "fmp", "twelve-data"),
    "hongkong_HSI": ("fmp", "twelve-data"),
    "fmp_theme": ("fmp", "sec-edgar"),
    "edgar": ("sec-edgar",),
    "cboe_put_call": ("cboe-daily",),
    "aaii_sentiment": ("aaii",),
    "coinbase_spot": ("coinbase",),
    "okx_funding": ("okx",),
    "okx_basis": ("okx", "coinbase"),
    "btc_etf_flow": ("sosovalue",),
    "events": ("trading-economics",),
}

SUPPLY_RECOMMENDATIONS: tuple[dict[str, str], ...] = (
    {
        "gap": "VIX、VVIX、Put/Call",
        "free": "FRED VIXCLS、Cboe Daily Market Statistics、Cboe VIX/VVIX 历史下载。",
        "freeCost": "¥0；已接入 Cboe/FRED/Cboe Daily，主要成本是本地存储和定时任务。",
        "value": "Alpha Vantage premium 或 EODHD options/constituents add-on。",
        "valueCost": "Alpha Vantage $49.99/月起（约¥339/月）；EODHD options/indices add-on $29.99/月起（约¥204/月）。",
        "quality": "Cboe DataShop/LiveVol、Bloomberg、LSEG。",
        "qualityCost": "通常询价；适合需要授权展示、逐笔/实时和商业再分发的场景。",
        "next": "优先补 VVIX 和 Put/Call 历史序列，低成本且最接近官方口径。",
        "refIds": "fred-vix,cboe-daily,cboe-vix,alpha-vantage,eodhd,bloomberg,lseg",
    },
    {
        "gap": "Fear & Greed",
        "free": "自建代理：VIX、put/call、动量、宽度、信用利差、避险需求。",
        "freeCost": "¥0；需要自己维护合成口径、历史回填和回测解释。",
        "value": "TradingView/YCharts/MacroMicro 等图表或情绪数据方案；也可用低价行情 API 自建。",
        "valueCost": "若走自建，通常复用 Alpha Vantage/FMP/Tiingo/EODHD，约 $22-59/月起（约¥149-401/月）。第三方情绪产品多需按页面重新核价。",
        "quality": "Bloomberg/LSEG/FactSet 工作流中自建并固化指标。",
        "qualityCost": "机构终端/数据许可通常询价或年度合同；适合正式投研工作流，不适合课程复现第一步。",
        "next": "不要冒充 CNN 原始值，先在页面标为 fear_greed_proxy。",
        "refIds": "cboe-daily,fred-vix,fmp,tiingo,twelve-data,factset,bloomberg,lseg",
    },
    {
        "gap": "SPX/NDX 成分股宽度",
        "free": "公开成分列表 + yfinance/Alpha Vantage 日线。",
        "freeCost": "¥0；缺点是当前成分代理，难以做到 point-in-time 历史成分。",
        "value": "FMP、EODHD、Tiingo、Twelve Data、Massive/Polygon、Nasdaq Data Link。",
        "valueCost": "FMP Starter $22/月（约¥149/月）；Tiingo Power $30/月（约¥204/月）；Twelve Data Grow from $29/月（约¥197/月）；Massive Stocks Starter $29/月（约¥197/月）；EODHD constituents $29.99/月（约¥204/月）。",
        "quality": "S&P Global、Nasdaq 官方、Bloomberg/LSEG point-in-time 成分。",
        "qualityCost": "官方指数成分和 point-in-time 授权通常询价；成本取决于指数、用途和再分发范围。",
        "next": "先用固定成分 CSV 做 20/50/200D 宽度，并标为 proxy。",
        "refIds": "alpha-vantage,fmp,eodhd,tiingo,twelve-data,massive,bloomberg,lseg",
    },
    {
        "gap": "SPX/NDX NTM PE 与 forward EPS",
        "free": "SEC XBRL + ETF 持仓 + trailing/forward 代理，或手工维护 CSV。",
        "freeCost": "¥0；只能做 proxy，forward EPS/NTM PE 很难免费稳定复现。",
        "value": "FMP/EODHD/Tiingo/Twelve Data fundamentals，自行按权重聚合。",
        "valueCost": "FMP Premium $59/月（约¥401/月）起更适合完整历史；EODHD corporate events/news $19.99/月（约¥136/月）和商业 all-in-one $399/月（约¥2,709/月）用于更正式覆盖；Tiingo fundamentals 为 add-on/询价。",
        "quality": "FactSet、Bloomberg、LSEG I/B/E/S、S&P Capital IQ Estimates。",
        "qualityCost": "一致预期/forward EPS 通常询价或企业合同；FactSet/S&P/LSEG/Bloomberg 官方页面以联系销售为主。",
        "next": "没有授权序列前只展示估值代理，不展示为正式 NTM PE。",
        "refIds": "sec-edgar,fmp,eodhd,tiingo,twelve-data,factset,bloomberg,lseg,sp-capital-iq",
    },
    {
        "gap": "宏观日历与事件",
        "free": "FRED、SEC EDGAR、公司 IR RSS、交易所公告、公开新闻 RSS。",
        "freeCost": "¥0；无授权新闻只保存标题、来源、URL 和来源链。",
        "value": "Trading Economics Calendar/API、FMP Calendar & News、Alpha Vantage News Sentiment、EODHD Calendar & News。",
        "valueCost": "Trading Economics Standard $149/月（约¥1,012/月，年付价）；FMP Starter/Premium $22-59/月（约¥149-401/月）；EODHD Calendar & News $19.99/月（约¥136/月）。",
        "quality": "Bloomberg News、LSEG/Reuters、Dow Jones/Factiva、S&P Global。",
        "qualityCost": "新闻和再分发授权通常询价；采购前必须确认正文存储、展示和再分发条款。",
        "next": "raw_events 已保留来源链；下一步补去重事件 ID、实体标签和授权新闻正文链路。",
        "refIds": "sec-edgar,trading-economics,fmp,eodhd,alpha-vantage,bloomberg,lseg",
    },
)

REPLICATION_DATA_ROWS: tuple[dict[str, str], ...] = (
    {
        "module": "市场情绪",
        "target": "Fear & Greed、VIX、VVIX/VIX、SPX/NDX 宽度、30 日趋势",
        "current": "VIX/VVIX、Cboe Put/Call、AAII、fear_greed_proxy、ETF 参与度代理",
        "status": "部分复现 / proxy",
    },
    {
        "module": "核心估值",
        "target": "SPX/NDX NTM PE、forward EPS、1y/5y/10y 分位",
        "current": "主题估值因子、valuation_rate_gap_proxy、可选 valuation panel 字段",
        "status": "缺授权估值 / proxy",
    },
    {
        "module": "回撤点位",
        "target": "SPY/QQQ 当前价、历史高点、回撤档位、隐含 PE",
        "current": "SPY/QQQ 当前价格；历史高点和 PE 依赖状态面板",
        "status": "价格侧部分复现",
    },
    {
        "module": "状态回测",
        "target": "FNG、VIX、50D breadth、NTM PE percentile 的历史近邻和 forward return",
        "current": "已有相似状态框架；缺真实目标特征历史和 forward return 面板",
        "status": "框架复现 / 数据缺口",
    },
    {
        "module": "策略实验室",
        "target": "自然语言策略解析、规则编译、回测和覆盖率",
        "current": "仅保留页面状态和缺口说明",
        "status": "未复现",
    },
    {
        "module": "Open Hub / 事件流",
        "target": "事件标题、来源链、实体、去重、收藏、媒体资产",
        "current": "raw_events 标题、来源、URL、sourceChain；无授权正文",
        "status": "部分复现",
    },
)

REPLICATION_MISSING_ROWS: tuple[dict[str, str], ...] = (
    {
        "gap": "CNN Fear & Greed 原始值",
        "impact": "不能展示为官方 CNN 数值，只能展示 fear_greed_proxy。",
        "bestNext": "保留自建代理；补 SPX 动量、真实宽度、信用利差和避险需求历史。",
    },
    {
        "gap": "SPX/NDX point-in-time 宽度",
        "impact": "无法复现目标站 20/50/200D 成分股宽度趋势。",
        "bestNext": "先固定当前成分 CSV + Tiingo/FMP/EODHD 日线；高质量再采购官方历史成分。",
    },
    {
        "gap": "指数级 NTM PE / forward EPS",
        "impact": "核心估值、EPS 归因、隐含 PE 都只能做 proxy。",
        "bestNext": "课程复现用手工/CSV valuation_panel；正式版采购 FactSet/S&P/LSEG/Bloomberg。",
    },
    {
        "gap": "宏观日历授权",
        "impact": "Trading Economics 401 时只能展示 simulated fallback events。",
        "bestNext": "低成本用 FMP/EODHD calendar；需要高覆盖再开 Trading Economics 或新闻授权。",
    },
    {
        "gap": "新闻正文、实体、媒体和收藏",
        "impact": "Open Hub 只能展示只读标题和来源链。",
        "bestNext": "先做去重 event_id 和实体标签；正文和媒体必须等授权链路确认。",
    },
)

REPLICATION_COST_NOTES: tuple[str, ...] = (
    "成本估算截至 2026-07-02；美元按 1 USD ≈ 6.79 CNY 粗略折算，未计税费、手续费、交易所授权和商用展示/再分发费用。",
    "页面里的价格用于课程复现和采购优先级判断；正式采购前必须重新核对官网、学校授权、个人/商业用途和数据存储条款。",
    "Bloomberg、LSEG、FactSet、S&P Capital IQ、Cboe DataShop/LiveVol、新闻正文授权多为询价制，本报告不编造固定价格。",
)


def _coverage_row(key: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _coverage(
    *,
    scores_doc: JsonDocument,
    actions_doc: JsonDocument,
    raw_market_doc: JsonDocument,
    status_doc: JsonDocument,
    cross_market_doc: JsonDocument,
    tushare_doc: JsonDocument,
    panel_doc: PanelDocument,
    neighbors: Sequence[Mapping[str, object]],
    neighbor_summary: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    themes = _as_list(scores_doc.data.get("themes"))
    sources = _as_list(status_doc.data.get("sources"))
    cross_markets = bool(_as_mapping(cross_market_doc.data.get("us_stocks"))) or bool(
        _as_mapping(cross_market_doc.data.get("macros"))
    )
    tushare_breadth = bool(_as_mapping(tushare_doc.data.get("breadth")))
    has_panel_state = any(
        _number(row.get("own_risk_appetite_score")) is not None for row in panel_doc.rows
    )
    has_participation = any(
        _number(row.get("rsp_spy_participation_proxy")) is not None for row in panel_doc.rows
    )
    has_valuation = any(
        _number(row.get("valuation_rate_gap_proxy")) is not None for row in panel_doc.rows
    )
    derived_panel = _panel_is_derived(panel_doc)
    risk_detail = (
        "未提供状态面板时，已从 Cboe/FRED VIX、Cboe Put/Call 和 AAII 自动派生代理指标。"
        if derived_panel
        else "可选状态面板代理指标，用于替代授权恐惧贪婪序列。"
    )
    participation_detail = (
        "未提供状态面板时，已用 RSP/SPY 或 SPY/QQQ ETF 相对表现自动派生参与度代理。"
        if derived_panel
        else "可选 RSP/SPY 参与度代理指标，用于观察宽度变化。"
    )
    valuation_detail = (
        "未提供状态面板时，已用主题估值因子和 10Y 美债收益率自动派生估值利率代理。"
        if derived_panel
        else "可选估值利率差代理指标，用于替代授权 NTM P/E 历史序列。"
    )
    return [
        _coverage_row(
            "daily_scores",
            "日报主题评分",
            "available" if themes else "missing",
            "来自 out/scores.json 的主题评分和因子拆解。",
        ),
        _coverage_row(
            "actions",
            "操作建议",
            "available" if actions_doc.exists else "missing",
            "来自 out/actions.json 的阈值触发建议；空列表也表示正常运行。",
        ),
        _coverage_row(
            "raw_market",
            "原始市场 ETL",
            "available" if raw_market_doc.exists else "missing",
            "原生 ETL 产物，包含指数、板块、主题、BTC 和情绪数据。",
        ),
        _coverage_row(
            "etl_health",
            "ETL 数据源健康状态",
            "available" if sources else "missing",
            "来自 out/etl_status.json 的各抓取器状态。",
        ),
        _coverage_row(
            "cross_market",
            "跨市场领先信号",
            "available" if cross_markets else "missing",
            "美股、商品、宏观指标和 A 股概念映射。",
        ),
        _coverage_row(
            "a_share_snapshot",
            "A 股轻量快照",
            "available" if tushare_breadth else "missing",
            "TuShare 涨跌家数、资金流、指数和涨跌停摘要。",
        ),
        _coverage_row(
            "risk_state",
            "风险偏好状态",
            "proxy" if has_panel_state else "missing",
            risk_detail,
        ),
        _coverage_row(
            "participation",
            "市场参与度",
            "proxy" if has_participation else "missing",
            participation_detail,
        ),
        _coverage_row(
            "valuation_state",
            "估值利率状态",
            "proxy" if has_valuation else "missing",
            valuation_detail,
        ),
        _coverage_row(
            "similar_states",
            "相似状态后续收益",
            "available" if neighbors and neighbor_summary else "missing",
            "状态面板存在后续收益字段时本地计算。",
        ),
    ]


def _source_manifest(
    docs: Sequence[JsonDocument],
    panel_doc: PanelDocument,
) -> list[dict[str, object]]:
    manifest: list[dict[str, object]] = []
    for doc in docs:
        manifest.append(
            {
                "path": str(doc.path),
                "exists": doc.exists,
                "error": doc.error,
            }
        )
    panel_path = str(panel_doc.path) if panel_doc.path else ""
    if not panel_path and _panel_is_derived(panel_doc):
        panel_path = "derived:free-source-proxy"
    manifest.append({"path": panel_path, "exists": panel_doc.exists, "error": panel_doc.error})
    return manifest


def _source_status_from_message(name: str, ok: bool, message: str) -> str:
    text = message.lower()
    if not ok:
        return "missing"
    if any(token in message for token in ("示例", "模拟")):
        return "simulated"
    if name == "events" and "事件日历已生成" in message:
        return "simulated"
    if any(token in text for token in ("fallback", "proxy")) or any(
        token in message for token in ("兜底", "代理", "降级")
    ):
        return "proxy"
    return "available"


def _reference_rows() -> list[dict[str, str]]:
    return [{**item, "index": str(index)} for index, item in enumerate(REFERENCE_SPECS, start=1)]


def _known_gap_rows(
    coverage: Sequence[Mapping[str, str]],
    terminal: Mapping[str, Any],
    etl_sources: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()

    def add(
        key: str,
        label: str,
        status: str,
        detail: str,
        ref_ids: Sequence[str] = (),
    ) -> None:
        if key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "key": key,
                "label": label,
                "status": status,
                "detail": detail,
                "refIds": list(ref_ids),
            }
        )

    for row in coverage:
        status = row.get("status", "")
        if status in {"missing", "proxy"}:
            add(
                row.get("key", ""),
                row.get("label", ""),
                status,
                row.get("detail", ""),
            )

    for module in _as_list(terminal.get("modules")):
        entry = _as_mapping(module)
        status = str(entry.get("status") or "")
        if status in {"missing", "proxy"}:
            add(
                f"module:{entry.get('key')}",
                str(entry.get("label", "")),
                status,
                str(entry.get("detail", "")),
            )

    for source in etl_sources:
        name = str(source.get("name", ""))
        ok = bool(source.get("ok"))
        message = str(source.get("message", ""))
        status = _source_status_from_message(name, ok, message)
        if status in {"missing", "simulated"}:
            add(
                f"etl:{name}:{message[:32]}",
                name,
                status,
                message,
                ETL_REFERENCE_IDS.get(name, ()),
            )
    return rows


def _source_analysis(
    *,
    status: Mapping[str, Any],
    coverage: Sequence[Mapping[str, str]],
    terminal: Mapping[str, Any],
) -> dict[str, object]:
    etl_sources = _etl_source_rows(status)
    current_sources: list[dict[str, object]] = []
    for source in etl_sources:
        name = str(source.get("name", ""))
        ok = bool(source.get("ok"))
        message = str(source.get("message", ""))
        current_sources.append(
            {
                "name": name,
                "status": _source_status_from_message(name, ok, message),
                "message": message,
                "refIds": list(ETL_REFERENCE_IDS.get(name, ())),
            }
        )
    return {
        "references": _reference_rows(),
        "currentSources": current_sources,
        "gaps": _known_gap_rows(coverage, terminal, etl_sources),
        "recommendations": [
            {
                **item,
                "refIds": [ref_id for ref_id in item["refIds"].split(",") if ref_id],
            }
            for item in SUPPLY_RECOMMENDATIONS
        ],
        "replicationReport": {
            "title": "目标网页端复现报告",
            "scope": "本页复现目标是市场全景终端的数据体验，不依赖目标站 API；所有运行时数据来自本仓库 ETL、快照和可选状态面板。",
            "dataRows": list(REPLICATION_DATA_ROWS),
            "missingRows": list(REPLICATION_MISSING_ROWS),
            "costNotes": list(REPLICATION_COST_NOTES),
            "fx": {"usdCny": USD_CNY_ASSUMPTION, "asOf": "2026-07-02"},
        },
        "footerNotes": [
            "页面引用只说明数据来源和口径，不代表已购买或接入所有参考供应商。",
            "available 表示本项目当前产物可直接渲染；proxy 表示使用自建或本地代理；simulated 表示使用示例/回退数据；missing 表示缺少必要输入或授权。",
            "授权估值、指数成分和新闻服务价格会变化，采购前需要重新核对官网、学校授权或合同条款。",
        ],
    }
