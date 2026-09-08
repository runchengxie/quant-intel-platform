# 网页看板数据源调研笔记

> 说明：本文是早期调研笔记，记录复现外部市场全景终端所需的数据源、当前缺口和可选供应商成本。项目自身的静态看板入口是 `dm dashboard`，产物为 `out/web_dashboard.html` 与 `out/web_dashboard_payload.json`。

## 三句话解读

1. 目前最缺的是未来十二个月市盈率（NTM PE）和未来十二个月预期每股盈利（forward 每股收益，即 EPS），性价比起点建议 FMP Premium（月付 $79/月，约 ¥536/月，年付折算约 $59/月，约 ¥401/月），高质量来源建议 FactSet Estimates 或 S&P Capital IQ Estimates（需询价）。
2. 第二梯队建议补标普 500 时点成分股数据，也就是历史上每一天按当时真实指数成分股计算市场宽度，性价比来源建议 EODHD Fundamentals Data Feed（$59.99/月，约 ¥407/月）或 All-in-One（$99.99/月，约 ¥679/月），高质量来源建议 S&P Global Index Data（需询价）。
3. 历史状态面板会在日更任务持续把每日状态追加到 `market_state_panel.csv` 后逐步补齐，短期仍建议回填至少 3 到 5 年的 VIX、宽度、估值和 forward return，避免刚上线时状态回测样本太少。

## 报告结论

本报告整理 `https://www.lucasgou.cloud/` 市场全景终端需要的数据源，并说明本项目当前已经复现的部分、仍缺的数据、可选供应商和大致成本。

当前项目已经做出一个静态网页看板，入口是 `dm dashboard`，产物是 `out/web_dashboard.html` 和 `out/web_dashboard_payload.json`。网页运行时只读取本仓库的 ETL 结果、快照文件和可选状态面板，不调用目标站接口。

当前结论可以概括为三点：

1. 市场情绪和跨市场行情已经具备可展示基础。VIX、VVIX、Cboe Put/Call、AAII、SPY/QQQ、黄金、DXY、10Y 美债等数据已经进入看板。
2. 估值和成分股宽度仍是主要缺口。SPX/NDX 的 NTM PE、forward EPS、估值分位、point-in-time 成分股宽度，通常需要商业数据源或手工维护面板。
3. 课程复现建议先走低成本路线。短期使用自建代理指标、固定成分 CSV、低价行情 API 和手工 valuation panel。正式投研版本再考虑 FactSet、Bloomberg、LSEG、S&P Capital IQ、Cboe DataShop 等高质量来源。

价格估算截至 2026-07-02，美元按 `1 USD ≈ 6.79 CNY` 粗略折算。实际采购前需要重新确认官网价格、学校授权、个人或商业用途、交易所授权、正文存储和数据再分发条款。

## 目标页面需要哪些数据

目标站首页是市场全景终端，核心体验围绕市场情绪、估值、回撤、状态回测和事件流展开。按页面模块拆分，需要的数据如下：

| 页面模块 | 需要的数据 | 用途 |
|----------|------------|------|
| 市场情绪 | Fear & Greed、VIX、VVIX/VIX、SPX/NDX 20/50/200 日宽度、30 日趋势 | 判断市场风险偏好、恐慌程度和内部参与度 |
| 核心估值 | SPX/NDX NTM PE、forward EPS、1 年、5 年、10 年分位 | 判断指数估值位置 |
| EPS 与估值归因 | 指数价格、forward EPS、forward PE、估值变化 | 拆解指数收益来自盈利还是估值扩张 |
| 回撤点位 | SPY/QQQ 当前价、历史高点、回撤幅度、隐含 PE、估值分位 | 展示不同回撤档位下的价格和估值 |
| 状态回测 | FNG、VIX、50D 宽度、NTM PE 分位、5/30/90/252 日后续收益 | 寻找相似历史状态，统计后续收益 |
| 策略实验室 | 自然语言策略、规则解析、标的识别、回测结果、覆盖率 | 支持用户输入策略并回测 |
| Open Hub 事件流 | 标题、来源、URL、实体标签、去重 ID、收藏状态、媒体资产 | 汇总新闻、财报、AI、金融动态 |

目标站接口观察到的字段包括：

| 接口样本 | 关键字段 | 对应模块 |
|----------|----------|----------|
| `/api/v1/sentiment/overview` | `fear_greed`、`vix`、`vol_structure`、`breadth.spx`、`breadth.ndx` | 市场情绪 |
| `/api/v1/sentiment/fear-greed/trend` | `series[].trade_date`、`series[].value` | Fear & Greed 趋势 |
| `/api/v1/sentiment/volatility/trend` | `vix_series`、`vol_structure_series` | 波动率趋势 |
| `/api/v1/sentiment/breadth/trend` | `above_20d_series`、`above_50d_series`、`above_200d_series` | 成分股宽度 |
| `/api/v1/valuation/timeline` | `current_value`、`percentile`、`series`、`valuation_source` | 估值时间线 |
| `/api/v1/valuation/price-attribution` | `total_return`、`eps_contribution`、`valuation_contribution`、`pe_start`、`pe_end` | 收益归因 |
| `/api/v1/valuation/drawdown-scenarios` | `current_price`、`high_price`、`current_drawdown_pct`、`scenarios[].implied_pe` | 回撤点位 |
| `/api/v1/market-regime/overview` | `conditions`、`metrics[].window_days`、`win_rate`、`avg_return` | 状态回测 |
| `/api/v1/strategy-lab/runs` | `strategy_spec`、`charts`、`data_coverage` | 策略实验室 |

## 当前项目已经接入的数据

本项目的网页看板已经把数据来源、代理口径和缺口说明写入页面，字段集中在 `sourceAnalysis`。页面对应的主要输入文件如下：

| 输入文件 | 作用 |
|----------|------|
| `out/scores.json` | 主题评分、因子拆解和主题估值代理 |
| `out/actions.json` | 阈值触发的操作建议 |
| `out/raw_market.json` | 原始市场 ETL 结果，包含指数、主题、BTC 和情绪数据 |
| `out/raw_events.json` | 事件流标题、来源、URL 和来源链 |
| `out/etl_status.json` | 各抓取器的健康状态 |
| `data-snapshots/latest/cross_market_snapshot.json` | 美股、宏观、商品和跨市场映射 |
| `data-snapshots/latest/tushare_snapshot.json` | A 股指数、涨跌家数、资金流和涨跌停 |
| `out/market_state_panel.csv` | 可选状态面板，用于历史回测、宽度、估值、回撤字段 |

已接入的数据源和用途如下：

| 数据源 | 当前状态 | 用在页面哪里 |
|--------|----------|--------------|
| Alpha Vantage | 可用 | 指数和主题行情主链路 |
| FMP | 可用，部分作为报价兜底 | 主题估值、行情兜底、财务代理 |
| SEC EDGAR | 可用 | 财报和 XBRL 基础数据 |
| Cboe VIX/VVIX 历史 CSV | 可用 | VIX、VVIX、`VVIX / VIX / 3.5` |
| Cboe Daily Market Statistics | 可用 | Put/Call 情绪指标 |
| FRED `VIXCLS` 和 10Y | 可用 | VIX 兜底、10Y 美债收益率 |
| AAII Sentiment | 可用 | 散户多空情绪 |
| yfinance 类快照 | 可用 | SPY、QQQ、SMH、美股大盘、黄金、DXY 等 |
| Coinbase、OKX | 可用 | BTC 现货、资金费率和永续基差 |
| SoSoValue | 可用 | BTC ETF 净流入 |
| TuShare | 可用 | A 股扩展模块 |
| RSS、SEC、公开网页 | 部分可用 | 事件标题、来源链和公开链接 |

当前页面已经能展示：

| 模块 | 当前实现 | 复现程度 |
|------|----------|----------|
| 市场情绪 | VIX、VVIX、Put/Call、AAII、`fear_greed_proxy`、SPY/QQQ 参与度代理 | 部分复现 |
| 核心估值 | 主题估值因子、`valuation_rate_gap_proxy`、可选 valuation panel 字段 | 代理复现 |
| 回撤点位 | SPY/QQQ 当前价格，可选历史高点和估值字段 | 价格侧部分复现 |
| 状态回测 | 已有相似状态框架，依赖状态面板历史列 | 框架已具备 |
| 策略实验室 | 页面保留入口和缺口说明 | 待实现 |
| 事件流 | 标题、来源、URL、`sourceChain` | 部分复现 |

## 当前缺口

| 缺口 | 影响 | 建议 |
|------|------|------|
| CNN Fear & Greed 原始值 | 页面只能展示 `fear_greed_proxy`，不能展示官方 CNN 数值 | 保留自建代理，补 SPX 动量、真实宽度、信用利差和避险需求 |
| SPX/NDX 成分股宽度 | 无法复现 20/50/200 日成分股宽度趋势 | 先用固定成分 CSV 加低价日线数据，后续采购 point-in-time 成分 |
| SPX/NDX NTM PE 和 forward EPS | 核心估值、收益归因和隐含 PE 只能做代理 | 先支持手工 `valuation_panel.csv`，正式版本采购一致预期数据 |
| 估值分位和历史收益 | 状态回测样本不足，无法复现目标站近邻统计 | 建立历史状态面板，补 5/30/90/252 日 forward return |
| 宏观日历授权 | Trading Economics 当前返回 401，事件日历只能走回退 | 低成本使用 FMP 或 EODHD 日历，高覆盖再采购 Trading Economics |
| 新闻正文和媒体资产 | Open Hub 只能展示标题和来源链 | 先补去重 ID 和实体标签，正文和媒体等授权确认后再接入 |
| HSI 行情 | Stooq 当前返回不足，港股指数缺失 | 改用 FMP、Twelve Data、港股 ETF 或交易所授权数据 |
| 策略实验室 | 暂无自然语言策略解析和回测结果 | 二期做规则模板，再接入大语言模型（LLM） 解析和回测沙箱 |

## 数据源补齐方案和成本

以下价格来自公开价格页面，人民币为粗略折算。机构级数据常见询价制，表中只写采购方向。

| 数据缺口 | 免费方案 | 性价比方案 | 高质量方案 | 推荐落地 |
|----------|----------|------------|------------|----------|
| VIX、VVIX、Put/Call | 已接入 Cboe、FRED 和 Cboe Daily。成本 ¥0，主要成本是定时任务和存储。 | Alpha Vantage Premium，$49.99/月起，约 ¥339/月。EODHD options/indices add-on，$29.99/月起，约 ¥204/月。 | Cboe DataShop、LiveVol、Bloomberg、LSEG，通常询价。 | 已有单日快照，下一步沉淀历史序列。 |
| Fear & Greed | 自建 `fear_greed_proxy`，成本 ¥0。需要维护合成口径和历史。 | 复用 FMP、Tiingo、Twelve Data、EODHD 等低价行情源，约 $22 到 $59/月，约 ¥149 到 ¥401/月。 | Bloomberg、LSEG、FactSet 工作流内自建，或采购授权情绪数据。 | 保留自建代理，不使用目标站接口。 |
| SPX/NDX 成分和宽度 | 公开成分列表加 yfinance 或 Alpha Vantage 免费额度。成本 ¥0。缺点是历史成分不完整。 | FMP Starter，$22/月，约 ¥149/月。Tiingo Power，$30/月，约 ¥204/月。Twelve Data Grow 起步 $29/月，常用月付 $79/月，约 ¥197 到 ¥536/月。EODHD Fundamentals，$59.99/月，约 ¥407/月，含 S&P 500 历史成分接口。 | S&P Global、Nasdaq 官方、Bloomberg、LSEG，通常询价。 | 先用固定成分 CSV 做 20/50/200 日宽度，标为 `proxy`。 |
| 指数和 ETF 日线、历史高点 | yfinance、Alpha Vantage compact 日线、Nasdaq Data Link 免费数据。成本 ¥0。 | FMP、Tiingo、Twelve Data、Massive、EODHD，约 $22 到 $30/月起，约 ¥149 到 ¥204/月起。 | Bloomberg、LSEG、S&P Global、Nasdaq Data Link premium，通常询价。 | 先补价格回撤档位，投入低，展示效果明显。 |
| SPX/NDX NTM PE、forward EPS | SEC XBRL 加 ETF 持仓做 trailing 或 proxy，也可以手工维护 CSV。成本 ¥0。 | FMP Premium 月付 $79/月，约 ¥536/月，年付折算约 $59/月，约 ¥401/月。Twelve Data Grow 起步 $29/月，常用月付 $79/月，约 ¥197 到 ¥536/月。EODHD Fundamentals，$59.99/月，约 ¥407/月，或 All-in-One，$99.99/月，约 ¥679/月。 | FactSet Estimates、Bloomberg Data License、LSEG Datastream、I/B/E/S、S&P Capital IQ Estimates，通常询价。 | 课程复现先接 `valuation_panel.csv`，正式版本采购一致预期。 |
| EPS 与估值归因 | trailing EPS 或 earnings yield 演示归因。成本 ¥0。 | FMP Premium 月付 $79/月，约 ¥536/月，年付折算约 $59/月，约 ¥401/月。EODHD Fundamentals、Tiingo Power、Twelve Data Grow 加指数权重自行聚合，约 $30 到 $79/月起，约 ¥204 到 ¥536/月起。 | FactSet、Bloomberg、LSEG、S&P 的一致预期和指数聚合数据，通常询价。 | 等 NTM PE 和 forward EPS 稳定后再打开正式模块。 |
| 宏观日历和事件 | FRED、SEC EDGAR、公司 IR RSS、交易所公告、公开新闻 RSS。成本 ¥0。 | Trading Economics Standard，$149/月，约 ¥1,012/月。FMP Starter 或 Premium，$22 到 $59/月，约 ¥149 到 ¥401/月。EODHD Calendar & News，$19.99/月，约 ¥136/月。 | Bloomberg News、LSEG News、Reuters、Dow Jones、Factiva、S&P Global，通常询价。 | 无授权新闻只保存标题、来源和 URL。 |
| A 股行情和资金流 | 交易所公开数据、AkShare。成本 ¥0。 | TuShare Pro、聚宽、米筐，按官网和账号权限核价。 | Wind、Choice、同花顺 iFinD，通常按年、席位和模块报价。 | 作为本项目增强模块保留。 |
| 回测状态面板 | 本地 CSV，由 yfinance、FRED、Cboe 和自建宽度脚本每日追加。成本 ¥0。 | DuckDB 或 Parquet 本地因子库，加 FMP、EODHD、Tiingo、Twelve Data、Massive，约 $22 到 $79/月起，约 ¥149 到 ¥536/月起。 | Bloomberg、LSEG、S&P、FactSet 的 point-in-time 数据湖，通常询价。 | 先稳定 `market_state_panel.csv` 字段契约。 |

## 建议落地顺序

1. 先把 VIX、VVIX、Put/Call、AAII、SPY/QQQ、10Y 和主题估值持续写入状态面板。这样市场情绪和风险偏好趋势可以稳定展示。
2. 用固定成分 CSV 加低价日线数据补 SPX/NDX 20/50/200 日宽度。页面标记为 `proxy`。
3. 增加 `valuation_panel.csv`，支持手工或授权导入 SPX/NDX NTM PE、forward EPS 和估值分位。
4. 用 SPY/QQQ 历史价格补 5/30/90/252 日 forward return，打开状态近邻统计。
5. 替换 HSI 数据源，减少 Stooq 对港股模块的影响。
6. 宏观事件先使用 FMP、EODHD 或公开 RSS，Trading Economics 等确认凭证和套餐后再接入。
7. 事件流先补 `event_id`、实体标签和去重规则，新闻正文和图片视频等授权明确后再保存。
8. 策略实验室放到二期，先做固定规则模板，再接自然语言解析。

## 看板生成方式

网页看板由以下命令生成：

```bash
uv run dm dashboard
```

默认输出：

| 输出文件 | 用途 |
|----------|------|
| `out/web_dashboard.html` | 静态网页看板，可以本地打开或发布到静态站点 |
| `out/web_dashboard_payload.json` | 结构化数据，便于测试、排查和下游复用 |

可选状态面板：

```bash
uv run dm state-panel --period 10y --timeout 30
uv run dm dashboard --state-panel path/to/market_state_panel.csv
```

`dm state-panel` 会尝试从 FRED、Cboe VIX/VVIX、Cboe Put/Call 和 yfinance 生成 `out/market_state_panel.csv`。需要 SPX/NDX 成分股宽度时可以追加 `--include-breadth --breadth-mode sample`，但这是慢任务，建议先输出到单独 CSV 检查质量。

未传入 `--state-panel` 时，`dm dashboard` 会依次检查 `MARKET_STATE_PANEL` 和 `out/market_state_panel.csv`。如果没有显式状态面板，页面会从 Cboe/FRED VIX、Cboe Put/Call、AAII、SPY/QQQ、主题估值和 10Y 美债收益率派生一行代理状态。该行会标为 `derived:free-source-proxy`，只能代表当前一日，不能替代历史状态面板。

状态面板建议字段：

| 字段 | 用途 |
|------|------|
| `date` | 日期 |
| `own_risk_appetite_score` | 自建风险偏好 |
| `rsp_spy_participation_proxy` | 市场参与度代理 |
| `valuation_rate_gap_proxy` | 估值利率差代理 |
| `spx_above_50d_pct`、`ndx_above_50d_pct` | SPX/NDX 50 日宽度 |
| `spy_high`、`qqq_high`、`spy_52w_high`、`qqq_52w_high` | SPY/QQQ 高点 |
| `spx_ntm_pe`、`ndx_ntm_pe`、`spy_ntm_pe`、`qqq_ntm_pe` | 指数或 ETF 估值代理 |
| `spx_ntm_pe_percentile`、`ndx_ntm_pe_percentile` | 估值分位 |
| `vix`、`spy_close`、`sp500_close`、`ten_year_yield`、`hy_oas` | 最新状态指标 |
| `spy_forward_return_fwd_90d`、`spy_forward_return_fwd_252d`、`spy_forward_return_fwd_1260d`、`spy_forward_return_fwd_2520d` | 后续收益 |

## 覆盖口径

页面使用四类状态标记：

| 状态 | 含义 |
|------|------|
| `available` | 当前项目已有原生数据，可以直接展示 |
| `proxy` | 使用自建或本地代理指标，需要在页面说明口径 |
| `simulated` | 使用示例、模拟或本地回退数据 |
| `missing` | 缺少输入文件、关键字段、有效凭证或授权 |

无授权新闻只保存标题、来源和 URL。估值、宽度、Fear & Greed 这类字段如果来自代理口径，页面统一标为 `proxy`。

## 参考来源

| 数据类型 | 参考来源 |
|----------|----------|
| VIX 和宏观序列 | [FRED API](https://fred.stlouisfed.org/docs/api/fred/)、[FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS) |
| VIX、VVIX、Put/Call | [Cboe VIX Historical Data](https://www.cboe.com/tradable-products/vix/vix-historical-data/)、[Cboe Daily Market Statistics](https://www.cboe.com/markets/us/options/market-statistics/daily/) |
| 投资者情绪 | [AAII Investor Sentiment Survey](https://www.aaii.com/sentimentsurvey) |
| 公司财报和 XBRL | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) |
| 股票日线和基础行情 | [Alpha Vantage Documentation](https://www.alphavantage.co/documentation/)、[Nasdaq Data Link API](https://www.nasdaq.com/solutions/data/nasdaq-data-link/api)、[Nasdaq Data Link Docs](https://docs.data.nasdaq.com/docs/getting-started) |
| 中低价基础数据 | [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs/pricing)、[EODHD](https://eodhd.com/pricing)、[Tiingo](https://www.tiingo.com/pricing)、[Twelve Data](https://twelvedata.com/pricing)、[Massive](https://massive.com/pricing) |
| 宏观日历和新闻 | [Trading Economics Calendar API](https://tradingeconomics.com/api/calendar.aspx)、[FMP Calendar & News](https://site.financialmodelingprep.com/pricing-plans) |
| 一致预期和估值 | [FactSet Consensus Estimates](https://insight.factset.com/resources/factset-consensus-estimates-datafeed)、[Bloomberg Data License](https://professional.bloomberg.com/products/data/data-management/data-license/)、[LSEG Datastream](https://www.lseg.com/en/data-analytics/products/datastream-macroeconomic-analysis)、[S&P Capital IQ Estimates](https://www.spglobal.com/market-intelligence/en/solutions/capital-iq-estimates) |
| A 股扩展 | [TuShare](https://tushare.pro/) |
