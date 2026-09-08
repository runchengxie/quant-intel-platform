# 产物契约

以下 JSON 结构定义了关键文件的最小字段集。任何破坏这些契约的改动都视为破坏性变更。

## `out/etl_status.json`

```json
{
  "date": "2024-04-01",
  "ok": true,
  "sources": [
    {"name": "market", "ok": true, "message": ""},
    {"name": "cboe_put_call", "ok": false, "message": "使用上期数据"}
  ]
}
```

- `ok=false` → 进入降级模式
- `sources` 记录每个抓取器的状态

## `out/scores.json`

```json
{
  "date": "2024-04-01",
  "degraded": false,
  "themes": [
    {
      "name": "ai",
      "label": "AI",
      "total": 82.3,
      "breakdown": {
        "fundamental": 78.0, "valuation": 65.0,
        "sentiment": 58.0, "liquidity": 62.0, "event": 55.0
      },
      "breakdown_detail": {
        "fundamental": {"value": 78.0, "source": "主题行情"}
      },
      "weights": {
        "fundamental": 0.3, "valuation": 0.15,
        "sentiment": 0.25, "liquidity": 0.2, "event": 0.1
      },
      "meta": {"previous_total": 79.8, "delta": 2.5},
      "degraded": false
    }
  ],
  "events": [
    {"title": "收益季焦点", "date": "2024-04-02", "impact": "high"}
  ],
  "thresholds": {"action_add": 75, "action_trim": 45},
  "sentiment": {"score": 56.0, "put_call": 52.0, "aaii": 48.0},
  "config_version": 2,
  "config_changed_at": "2024-04-01"
}
```

必需字段：`date`、`degraded`、`themes[]`（含 `name`、`label`、`total`、`breakdown`、`weights`）。

可选字段：`breakdown_detail`、`meta`、`sentiment`、`config_version`。

## `out/actions.json`

```json
{
  "date": "2024-04-01",
  "items": [
    {"action": "关注增强", "name": "AI", "reason": "总分高于关注增强阈值"}
  ]
}
```

未命中阈值时 `items` 为空数组。

## `out/raw_events.json`

ETL 写出的事件流原始产物。无授权新闻只保存可审计元数据，不保存正文摘要或模型自由文本。

```json
{
  "events": [
    {
      "title": "CPI 发布",
      "date": "2026-07-02",
      "impact": "high",
      "source": "Trading Economics",
      "url": "https://tradingeconomics.com/calendar",
      "sourceChain": [
        {
          "source": "Trading Economics",
          "url": "https://tradingeconomics.com/calendar",
          "title": "CPI 发布"
        }
      ]
    }
  ],
  "ai_updates": [
    {
      "title": "OpenAI Update",
      "date": "2026-07-02",
      "source": "https://openai.com/news/rss.xml",
      "url": "https://openai.com/news/example",
      "sourceChain": [
        {
          "source": "https://openai.com/news/rss.xml",
          "url": "https://openai.com/news/example",
          "title": "OpenAI Update"
        }
      ]
    }
  ]
}
```

`events[]` 和 `ai_updates[]` 允许字段：`title`、`date`、`impact`、`country`、`source`、`url`、`published_at`、`market`、`label`、`category`、`sourceChain`。

`sourceChain[]` 条目允许字段：`source`、`url`、`title`。`url` 必须是 `http://` 或 `https://`。

禁止在 `raw_events.json` 的无授权新闻条目保存正文类字段：`summary`、`raw_text`、`news_text`、`items`、`rejected_items`、`fallback_errors`。需要摘要正文的报告应使用通过新闻契约校验的结构化新闻产物，不应从 `raw_events` 读取模型自由文本。

## `out/digest_card.json`

飞书互动卡片 JSON。必需结构：`header`（含 `title`）、`elements[]`（含 `div` 文本块和 `action` 按钮）。降级时 title 追加数据延迟标注。

## DailyWatch20 正式产物

research-workspace 发布、由 `scripts/daily_watch20_delivery.sh` 消费的 DailyWatch20 正式 artifact。
该产物遵循 research-workspace 的公开 schema，用于表达已准入的关注清单，不表达执行目标。

最小字段：

| 字段 | 说明 |
| --- | --- |
| `signal_date` | 信号日期，`YYYYMMDD` |
| `symbol` | A 股代码 |
| `raw_pred` | 候选池原始分 |
| `signal_eval` | 评估分 |
| `signal_backtest` | 回测分 |
| `signal_direction` | 多头方向，当前固定为 `1.0` |
| `rank` | 当日排名 |
| `model_version` | 信号模型版本 |
| `feature_set_id` | 特征/信号口径 |
| `eligible_for_backtest` | 是否可用于回测 |
| `eligible_for_live` | 是否可用于 live 候选 |

可选解释字段包括 `daily_confirm_score`、`trend_score`、`volume_score`、`risk_score`、
`ret_5d`、`ret_10d`、`close_to_20d_high`、`amount_ratio_20d`、`confidence_score`
和 `confidence_label`。这些列只增强候选信号解释与后续评估，不改变最小
`alpha_research.signals` 契约。

生产调度会同时生成 `signals.meta.json`，并通过 `hotsector validate-output` 检查来源能力、
候选数量和非空信号文件。若后续需要组合持仓，由 research-workspace 的
`hotsector_overlay` 显式消费该文件，若需要执行目标，再由 `strategy export-targets`
显式导出 `targets.json`。

`candidate_universe.json` 的来源门禁字段如下：

| 字段 | 说明 |
| --- | --- |
| `source_mode` | `normal`、`dc_fallback`、`event_fallback` 或 `blocked` |
| `fallback_reason` | `normal` 时为 `null`，其余模式记录稳定原因码 |
| `source_gate` | `hotsector_source_gate.v1` 审计对象，记录观测日、映射完整性、精确日事件确认源和逐源行数/日期/完整性 |

四态生产规则：

- `normal`：目标日 KPL 题材成分未触及接口行数上限（或有显式完整性 receipt），每行 `name/con_code/con_name` 映射键完整，且至少两个目标日事件确认源可用。
- `dc_fallback`：KPL 不满足完整映射，但目标日 DC 题材与成分可用，且 `manifest.completeness.trade_dates[目标日].complete=true`、行数/页数/终止页/题材覆盖率均与分区一致，同时至少两个事件确认源可用。
- `event_fallback`：无完整成员映射，但至少两个目标日事件确认源可用，客户展示必须明确标记事件型降级版。
- `blocked`：目标日事件确认源不足两个，停止 AI 选股与投递。

事件确认源固定为 `limit_list_ths`、`limit_step`、`limit_cpt_list`、`ths_hot`。
每项的每一行都必须包含合法且等于 `observation_date` 的日期，空值、非法日期和旧日数据均不得替代目标日。旧版候选若没有
`source_gate`，只允许沿用具备 KPL 和至少两个事件源的 normal 路径，不能推断降级模式。

## `out/web_dashboard_payload.json`

`dm dashboard` 生成的静态看板载荷。HTML 会内嵌同一份 payload，JSON 文件用于测试、排障和下游消费。

```json
{
  "title": "市场情报看板",
  "generatedAt": "2026-06-30 10:00 UTC",
  "latest": {
    "date": "2026-06-30",
    "riskAppetite": 64.0,
    "riskAppetiteLabel": "Neutral",
    "participation": 0.02,
    "participationLabel": "Mixed participation",
    "valuationRateGap": 0.5,
    "valuationRateGapLabel": "Balanced",
    "vix": 17.2,
    "spyClose": 489.0
  },
  "marketIntel": {
    "themes": [{"name": "ai", "label": "AI", "total": 82.0}],
    "actions": [],
    "etlSources": []
  },
  "crossMarket": {
    "usStocks": [],
    "commodities": [],
    "macros": [],
    "leadLag": []
  },
  "aShare": {
    "tradeDate": "20260630",
    "breadth": {"upCount": 2600, "downCount": 2100}
  },
  "coverage": [
    {"key": "daily_scores", "label": "日报主题评分", "status": "available"}
  ],
  "sourceAnalysis": {
    "references": [
      {
        "id": "alpha-vantage",
        "index": "1",
        "label": "Alpha Vantage",
        "title": "Alpha Vantage API",
        "url": "https://www.alphavantage.co/documentation/",
        "kind": "行情"
      }
    ],
    "currentSources": [
      {
        "name": "market",
        "status": "proxy",
        "message": "指数来源 SPX:alpha_vantage，降级 2 项",
        "refIds": ["alpha-vantage"]
      }
    ],
    "gaps": [
      {
        "key": "risk_state",
        "label": "风险偏好状态",
        "status": "missing",
        "detail": "可选状态面板代理指标缺失",
        "refIds": []
      }
    ],
    "recommendations": [
      {
        "gap": "VIX、VVIX、Put/Call",
        "free": "FRED/Cboe 公开数据",
        "value": "Alpha Vantage 或 EODHD options",
        "quality": "Cboe DataShop、Bloomberg、LSEG",
        "next": "先补 VVIX 和 Put/Call 历史序列",
        "refIds": ["fred-vix", "cboe-daily", "cboe-vix"]
      }
    ],
    "footerNotes": []
  }
}
```

必需顶层字段：`title`、`generatedAt`、`latest`、`marketIntel`、`crossMarket`、`aShare`、`coverage`、`sourceManifest`、`sourceAnalysis`。

`coverage[].status`、`sourceAnalysis.currentSources[].status`、`sourceAnalysis.gaps[].status` 取值：

- `available`：项目已有原生数据并可渲染
- `proxy`：本地代理指标存在，属于自建替代序列
- `simulated`：使用示例、模拟或本地回退数据，不能当作真实 `API` 原始数据
- `missing`：输入文件或关键字段缺失

`sourceAnalysis.references[].id` 是引用源稳定 ID，页面中的 `refIds[]` 必须指向这些 ID。引用只说明来源口径或建议供应商，不代表项目已经购买或接入所有参考源。

可选状态面板 CSV 字段见 [web-dashboard.md](web-dashboard.md)。状态面板缺失不能导致 `dm dashboard` 失败。

## `state/sentiment_history.json`

```json
{
  "put_call_equity": [0.72, 0.68, 0.65],
  "aaii_bull_bear_spread": [-10.0, -8.5]
}
```

保留近 252 个 Put/Call 值和 104 个 AAII 值。

## `data-snapshots/cross-market/YYYY-MM-DD.json`（跨市场快照）

由 `cross-market.yml` 在工作日 05:00 中国标准时间（CST） 生成并 commit 到仓库。

```json
{
  "date": "2024-04-01",
  "us_stocks": {
    "NVDA": {"close": 903.56, "pct_chg": 3.12},
    "AAPL": {"close": 170.03, "pct_chg": -0.85},
    "8035.T": {"close": 27750.00, "pct_chg": 1.45},
    "000660.KS": {"close": 242000.00, "pct_chg": 2.35},
    "SPY": {"close": 523.07, "pct_chg": 0.32}
  },
  "global_lead_lag": [
    {
      "concept": "存储芯片",
      "avg_pct_chg": 2.11,
      "signal": "bullish",
      "drivers": ["000660.KS +2.4%", "005930.KS +1.8%"],
      "markets": ["KR"],
      "total_weight": 2.3
    }
  ],
  "commodities": {
    "GC=F": {"close": 2342.50, "pct_chg": 1.20},
    "SLV": {"close": 28.15, "pct_chg": 2.10},
    "GLD": {"close": 215.80, "pct_chg": 0.98}
  },
  "macros": {
    "DX-Y.NYB": {"close": 104.50, "pct_chg": -0.15},
    "^VIX": {"close": 13.65, "pct_chg": -2.50},
    "^VVIX": {"close": 86.25, "pct_chg": 1.10},
    "^TNX": {"close": 4.21, "pct_chg": -0.71}
  },
  "aaii_sentiment": {
    "bullish_pct": 38.5,
    "bearish_pct": 25.3,
    "neutral_pct": 36.2,
    "as_of": "2024-03-27"
  },
  "cboe_putcall": {
    "as_of_date": "2026-06-29",
    "vix": 13.65,
    "vix_pct_chg": -2.50,
    "source": "fred_vixcls"
  },
  "errors": []
}
```

必需字段：`date`、`us_stocks`（至少包含 `close` 和 `pct_chg`）、`commodities`、`macros`。

可选字段：`global_lead_lag`、`aaii_sentiment`、`cboe_putcall`、`errors`（各抓取器失败时收集错误信息，非阻塞）。`macros.^VIX` 优先来自 Cboe 公开 VIX 历史 CSV，FRED `VIXCLS` 可作为兜底，`macros.^VVIX` 来自 Cboe 公开 VVIX 历史 CSV。`cboe_putcall` 为历史字段名，live 快照仍写入 VIX 恐贪摘要。FRED 失败时不再回退到 2019 年已停更的 CBOE put/call CSV。`global_lead_lag` 是全球领先资产按权重映射到 A 股概念后的结果，兼容旧的 `concept_mapping` 消费方。

## `data-snapshots/tushare/YYYY-MM-DD.json`（TuShare 轻量快照）

由 `tushare-daily.yml` 在工作日 09:30 CST 生成并 commit 到仓库。

```json
{
  "trade_date": "20260626",
  "generated_at": "2026-06-29T09:30:05+08:00",
  "indices": {
    "000001.SH": {
      "name": "上证指数",
      "close": 4027.26,
      "pct_chg": -2.26,
      "vol": 123456789.0,
      "amount": 9876543210.0
    }
  },
  "breadth": {
    "up_count": 790,
    "down_count": 4676,
    "flat_count": 47,
    "up_pct": 14.3,
    "down_pct": 84.8,
    "total_amount": 3579668000.0,
    "total_stocks": 5513,
    "avg_pct_chg": -2.5,
    "median_pct_chg": -2.3
  },
  "moneyflow": {
    "total_buy_elg_vol": 500000000.0,
    "total_sell_elg_vol": 680000000.0,
    "total_net_mf_amount": -180000000.0,
    "top_entries": [
      {
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "buy_elg_vol": 100000000.0,
        "sell_elg_vol": 80000000.0,
        "net_mf_amount": 20000000.0
      }
    ]
  },
  "limit_list": {
    "up": [
      {"ts_code": "600000.SH", "name": "浦发银行", "pct_chg": 10.02, "close": 12.50}
    ],
    "down": [],
    "_unavailable": false
  },
  "errors": []
}
```

必需字段：`trade_date`、`indices`、`breadth`、`moneyflow`。

可选字段：`limit_list`（免费令牌无此权限时为 `_unavailable: true`）、`errors`（各抓取器失败时收集错误信息，非阻塞）。

## `out/a_share_daily/ai_market_news.json`（结构化市场新闻）

由 `scripts/fetch_ai_market_news.py` 生成。大语言模型（LLM）/search 只作为检索器，最终报告只消费通过校验的 `items[]`，不直接消费自由文本。

```json
{
  "fetched_at": "2026-06-30T07:00:00+00:00",
  "model": "glm-4.6",
  "markets_requested": ["cn", "jp", "kr", "us"],
  "markets": {
    "cn": {
      "market": "cn",
      "label": "A股",
      "items": [
        {
          "market": "cn",
          "label": "A股",
          "category": "policy",
          "title": "政策标题",
          "summary": "一句话事实摘要。",
          "source": "来源名称",
          "url": "https://example.com/news",
          "published_at": "2026-06-30"
        }
      ],
      "news_text": "- [policy] 一句话事实摘要。（来源名称: [政策标题](https://example.com/news)）"
    }
  }
}
```

必需字段：`markets`。每个可用于报告的 `items[]` 条目必须包含 `title`、`summary`、`source`、`url`、`published_at`。缺少 `url` 或来源的条目必须被过滤，不进入 `morning-report`。

## A 股晚报市场温度

`evening_review.json` 的 `market_temperature` 是确定性解释层，最小结构为：

```json
{
  "trade_date": "20260715",
  "calibration": "provisional_observation_scale",
  "position_mapping": null,
  "heat_score": 44.4,
  "fragility_score": 59.2,
  "status_label": "结构分化且脆弱",
  "dimensions": {
    "liquidity": {"label": "流动性", "score": 5.9, "coverage": 1.0},
    "breadth": {"label": "广度", "score": 60.0, "coverage": 1.0},
    "profit_effect": {"label": "赚钱效应", "score": 82.3, "coverage": 0.67},
    "loss_risk": {"label": "亏钱风险", "score": 77.8, "coverage": 0.67},
    "trend_confirmation": {"label": "趋势确认", "score": 3.2, "coverage": 1.0},
    "rotation_quality": {"label": "轮动质量", "score": 82.8, "coverage": 1.0}
  },
  "core_tensions": [],
  "validation_conditions": [],
  "previous_validation": [],
  "metrics": {},
  "confidence": 0.97,
  "data_warnings": []
}
```

六个维度键固定，可用证据不足时 `score` 必须为 `null`，不能补零。`loss_risk` 的方向与其他维度相反，且必须同时保留独立的 `fragility_score`。`confidence` 只表示数据完整度，`calibration` 表示暂定观察刻度，消费者不得把任何观察分转换为仓位或交易指令。`validation_conditions` 使用 `metric/operator/target` 机器条件，下一交易日的 `previous_validation.status` 只允许 `confirmed`、`invalidated`、`not_evaluable`。

## DailyWatch20 逐股热点热度输入

`strategy watchlist20 news-heat-export`（由 research-workspace/strategy-pipeline 提供）将当日
hot-sector 候选发布为严格日期化的可选模型输入。`market-intel` 不再提供该生产命令或生产实现，
只在日报链路中消费已发布 artifact。
默认根目录为
`$DATA_PLATFORM_ROOT/strategy_inputs/watchlist20/news_heat/`，可用
`WATCHLIST20_NEWS_HEAT_ROOT` 覆盖。该变量始终表示发布父目录，不能直接指向
`latest`，producer 的 export、复用校验和策略输入都从该父目录派生同一个
`latest`。`latest` 是原子更新的相对符号链接，指向
`runs/<source_date>_<generated_at>_<hash>/`。每个 run 包含：

- `news_heat.csv`：稀疏正例逐股热度，
- `news_heat_receipt.json`：日期、来源、校验状态、校验和与时点（PIT）策略，
- `news_heat_schema.json`：列类型和缺失语义。

CSV v1 列：

```text
source_date,data_as_of,symbol,name,news_heat_score,heat_rank,source_kind,
source_topics,source_concepts,upstream_relevance,upstream_score,
upstream_confidence_score
```

`news_heat_score` 直接复用按同一 `source_date` 构建的 hotsector `relevance`，范围
为 `[0,1]`。`source_kind` 固定为 `structured_market_hotspot`。该面板采用
`sparse_positive_only` 覆盖：未出现的股票表示未知，不表示热度为零。

当前结构化 AI 新闻有来源 URL 和 `published_at` 校验，但没有经验证的股票代码映射，
因此 v1 不做标题/公司名模糊匹配，也不把 LLM 自由文本映射为逐股分数。历史 rerun 的
`candidate_universe.json` 可能同时包含 `quality_report` / `outcome_report`，导出器只读取
候选白名单字段并明确禁止消费这些未来评估字段。

research-workspace 生产者准入时必须调用等价于
`validate_news_heat_artifact(..., expected_source_date=...)` 的检查：receipt 和质量状态均为
`passed`、`source_date == data_as_of == expected_source_date`、市场范围仅 `sh-sz`、行数达到
约定下限、CSV 校验和和列顺序一致、股票唯一、分数有限且位于 `[0,1]`、排名连续。
`unavailable` artifact 包含带表头的空 CSV 和明确原因，它不得影响 B 袖资格，生产者
该可选增强项应禁用，不要补零或沿用旧日分数。

示例：

```bash
DATA_PLATFORM_ROOT=~/data/market-data-platform \
  uv run --project "$STRATEGY_PIPELINE_ROOT" strategy watchlist20 news-heat-export \
    --source-date 20260710
```

## DailyWatch20 正式选股产物

`market-intel` 只消费该 artifact 并负责展示，不复制模型打分或选股逻辑。默认目录为
`~/data/market-data-platform/strategy_outputs/watchlist20/latest/`，可用
`WATCHLIST20_ROOT` 覆盖。目录内必须同时存在：

- `watchlist_20.csv`：20 行正式观察池。
- `selection_receipt.json`：生产者的校验回执。
- `watchlist_20.json`：可选，存在时其股票、袖、排名和权重必须与 CSV 一致。

CSV 必需字段：

```text
signal_date,source_date,symbol,name,sleeve,rank,tracking_weight,
xgb_score,xgb_percentile,guard_score,final_score,industry,theme,
dual_confirmed,is_new,top_drivers,primary_risk,model_version,feature_set_id,data_as_of
```

`daily_watch20.selection.v2` 还要求每一行携带 `strategy_policy_id`，该值必须与
receipt 中的完整策略快照一致。

其中 `sleeve`、袖内排名、原始/约束/综合分、精确模型与特征集身份属于内部审计契约。客户 renderer 只展示统一 20 股清单、行业/主题、逐股关注理由与风险，不公开这些内部构造字段。

消费者兼容 `daily_watch20.selection.v1` 与 `daily_watch20.selection.v2`。v1 的
最小 `selection_receipt.json` 结构为：

```json
{
  "schema_version": "daily_watch20.selection.v1",
  "status": "passed",
  "source_date": "20260710",
  "signal_date": "20260713",
  "generated_at": "2026-07-10T18:00:00+08:00",
  "model_version": "DailyWatch20-XGB-v1",
  "feature_set_id": "daily_watch20_v1",
  "market_scope": "sh-sz",
  "counts": {"total": 20, "a": 4, "b": 16, "unique": 20},
  "tracking_weight_sum": 1.0,
  "minute_features": {
    "enabled": true,
    "as_of": "20260710",
    "required_date": "20260710",
    "lag_trade_days": 0
  }
}
```

v2 在上述回执上新增 `publication_tier=production`、`eligible_for_live=false`、
`strategy_policy_id` 和 `strategy_policy`。策略快照必须完整包含 `model`、`features`、
`label`、`candidate_pool`、`news_heat`、`construction`、`safety` 七段。消费者不只
重算 canonical SHA-256，还会独立验证各段必填字段、类型、允许值、数值范围，以及
训练策略、特征与标签、候选池、新闻热度、4+16 构造和发布安全之间的跨字段语义，
随后核对 receipt 与 CSV 的所有 policy carrier。只重算 hash 无法让语义无效的策略
进入晨报。

新的正式客户发布候选池固定为 `ths_hot_strict_v3`。`ths_hot_strict_v2` 仅用于历史产物
兼容读取。v3 策略身份必须编码
`max_missing_ranks=2`，回执同时携带原始 `missing_ranks` 与
`rank_coverage_status=complete|degraded`。排名 1 必须存在，其余名次最多允许两个源端
缺口。v2 仍按排名 1–20 的完整原语义校验。快照不得有排名并列或重复证券，去重、范围过滤和非正涨幅的行数必须守恒，组件
时间范围不得超过 180 秒，最大原始排名为 100，正涨池及模型可选交集均至少 20 只。
消费者会核对受保护 THS-hot 分区及其哈希，所选股票必须保留源快照的原始排名，例如
缺少 19 时，原第 20 名仍记录为 20，不重排，也不从全市场补位。任一证据不一致均
fail closed。存在一至两个合规缺口时，客户 Markdown、HTML 和 PNG 必须显示 TuShare
数据服务商疑似缺失部分热榜数据的提示，并列出缺失排名。`ths_hot_strict` v1 仅保留为
历史 artifact 的兼容读取模式，不再准入新的 production 策略。

准入检查包括：receipt 为 `passed`、指定源日期和预期信号日期完全匹配、仅沪深六位代码、20 个唯一股票、
A 袖 4 只、B 袖 16 只、袖内排名为连续的 `1..N`、分数字段均为有限数、行与 receipt 的
日期/模型/特征集一致，以及总跟踪权重为 1.0，v2 还必须通过完整策略契约和 carrier
一致性检查。任一检查失败时，正式 DailyWatch20 严格 fail closed，不发送任何替代股票
名单。旧 hotsector 池仅可作为本地研究产物，不得进入客户或内部正式投递。

## DailyWatch20 主题摘要产物

`research-workspace/strategy-pipeline` 从最终发布的 `watchlist_20.json` 生成同一 run 目录下的
`topic_summary.json`，`market-intel` 只消费该文件生成晨报热点主题分布图，不再读取旧的
`hotsector/candidate_universe.json`。当前契约为 `daily_watch20.topic_summary.v1`，其中
`topics[]` 含 `topic`、`count`、`weight`、`rank`，`aggregation` 固定为
`selected_watchlist_theme_count_and_weight`，`quality.status` 必须为 `passed`。

这里的 `weight` 是入选清单 `tracking_weight` 的聚合，不代表全市场题材热度。该 artifact 与
`watchlist_20.json`、`selection_receipt.json` 在同一目录发布并登记哈希。晨报默认将其视为可选
降级项，只有设置 `WATCHDOG_REQUIRE_TOPIC_SUMMARY=1`（或传入
`--require-topic-summary`）时 watchdog 才会因缺失、日期不匹配、契约失败或回执哈希不一致报警。

## DailyWatch20 正式投递回执

`out/a_share_daily/daily_watch20/<signal_date>/delivery_receipt.json` 使用
`daily_watch20_delivery.v1`。它至少包含：

```json
{
  "schema_version": "daily_watch20_delivery.v1",
  "product_id": "daily_watch20.cn.v1",
  "source_date": "20260728",
  "signal_date": "20260729",
  "source_receipt_origin": "/data/strategy_outputs/watchlist20/latest/selection_receipt.json",
  "source_receipt_path": "/repo/out/a_share_daily/daily_watch20/20260729/source_selection_receipt.json",
  "source_receipt_sha256": "<sha256>",
  "presentations": {
    "client": {
      "markdown_path": "/repo/out/a_share_daily/daily_watch20/20260729/client/daily_watch20.md",
      "markdown_sha256": "<sha256>",
      "image_path": "/repo/out/a_share_daily/daily_watch20/20260729/client/daily_watch20.png",
      "image_sha256": "<sha256>"
    }
  },
  "success": true,
  "targets": [
    {
      "audience": "client",
      "target_sha256": "<不可逆群目标指纹>",
      "messages": {
        "markdown": {
          "status": "sent",
          "content_sha256": "<sha256>",
          "message_id": "om_xxx"
        },
        "image": {
          "status": "sent",
          "content_sha256": "<sha256>",
          "message_id": "om_yyy"
        }
      }
    }
  ]
}
```

正式成功要求 client/internal 两类已配置 audience 都存在 Markdown 与图片的可确认
message id，消息内容 hash 必须等于对应 presentation，源 selection receipt 与渲染文件
必须仍存在且 hash 不漂移。目标只保存不可逆指纹，不把真实 chat id 写入回执。

## 变更规则

涉及契约字段、`config/weights.yml` 或模板的改动，必须在同一批直接推送到 `main` 的提交内：

1. 更新上述示例
2. 运行 `pytest -k contract`
3. 更新对应快照测试
