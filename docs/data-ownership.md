# 数据归属

本项目按外部数据产品、本项目轻量快照和代码化报告划分边界。Hermes 读取确定性事实材料，并负责后续点评。事实数据由代码生成。

日报框架属于代码契约：需要哪些数据、数据缺失时怎么降级、报告按什么顺序写、发到哪些群，都由 Python 和 shell 流水线控制。Agent 的职责放在事实材料之后，用来解释、补充和回答追问。

## 原则

1. 重型、历史、跨策略复用的数据由 `market-data-platform` 负责。
2. `market-intel` 不内嵌 `market-data-platform` 源码，也不把它作为子模块。
3. `market-intel` 可以保留轻量、报告专用、可持久化的快照。
4. 最终晨晚报由代码模板渲染。晚报状态、矛盾与验证条件来自确定性计算，大语言模型（LLM）/search 只允许产出带来源的候选新闻。
5. 无来源、无 URL、无法通过契约校验的新闻不得进入代码化报告。

## 数据边界

| 数据域 | 负责仓库 | `market-intel` 的用法 | 是否允许实时抓取 |
|---|---|---|---|
| A 股全量日频、资金流、概念、两融、指数、历史回测输入 | `market-data-platform` | 通过 `DATA_PLATFORM_ROOT/assets/tushare/a_share/` 只读 | 不允许在报告阶段补抓全量 |
| ETF rotation / hot-sector 原始输入 | `market-data-platform` | 子项目只读 `DATA_PLATFORM_ROOT` | 不允许写回数据湖 |
| DailyWatch20 候选池、策略计算和正式 artifact | `research-workspace` | `market-intel` 只读并校验 `WATCHLIST20_ROOT` | 由 owner 发布，market-intel 不重算 |
| 跨市场快照：美股、日韩、商品、宏观、情绪 | `market-intel` | `data-snapshots/cross-market/` 与 `latest/` | 允许快照缺失时兜底，并写回快照 |
| TuShare 轻量快照 | `market-intel` | `data-snapshots/tushare/`，供备份任务和便携环境读取 | 允许 GitHub Actions 定时轻量抓取 |
| GLM/Aliyun/Gemini 市场新闻 | `market-intel` | 只消费结构化 `items[]`：`title/source/url/published_at/summary` | 允许联网搜索，未通过校验则跳过 |
| 晨报/晚报文本 | `market-intel` | Python renderer 生成 Markdown/飞书消息 | 事实与确定性解释由代码生成 |

## `tushare_jobs` 迁移状态（与 `market-data-platform` 重叠收口）

`src/tushare_jobs/` 中部分任务与 `market-data-platform` 数据湖重复，应按 2026-07-29 整合评估
报告收回唯一 owner。当前状态：

| 任务 | 与 MDP 关系 | 处置 |
|---|---|---|
| `stock_st.py` | MDP 发布 `stock_st` | 只读消费：验证 receipt 后导出兼容 CSV |
| `listed_company.py` | MDP 发布 `stock_company`/`stk_managers`/`share_float` | 只读消费。仅轻量 `stock_basic` 报告快照保留直抓 |
| `index_weight.py` / `index_weight_daily.py` | MDP 发布 raw + daily mirror | 只读消费：不再重抓或本地展开 |
| `lightweight_snapshot.py` | MDP 无等价轻量 JSON | 保留：报告专用离岸/备份快照 |
| 报告增强镜像（`mirror-a-share-*`） | 已走 MDP（`refresh_tushare_report_datasets.sh`） | 已迁，无重叠 |

所有 MDP-owned reference 消费都会验证 receipt schema、dataset、SHA-256 和行数。验证失败
明确退出，不回退到旧下载器。详见 `docs/boundary-contract.md`（第三节）。

2026-07-30 更新：MDP 已在 `feat/tushare-migration` 分支建成等价下载能力
（`providers/tushare_a_share_reference.py`，含全部 6 个数据集的 DatasetSpec、download、
drift_weight 展开与 publish），并注册到 `marketdata tushare download-a-share-reference` 等子命令。
MDP 现为这些数据集的权威 owner。market-intel 已改为消费
`<DATA_PLATFORM_ROOT>/assets/tushare/a_share/<dataset>/a_share_all_<dataset>_latest.parquet`
和 receipt，旧重抓分支已退役。

## 部署约定

`DATA_PLATFORM_ROOT` 指向数据湖根目录。`MDP_DIR` 指向 `market-data-platform` 代码仓库。默认约定：

```bash
export DATA_PLATFORM_ROOT=$HOME/data/market-data-platform
export MDP_DIR=$RESEARCH_WORKSPACE_ROOT/quant-market-data-platform
```

新机器或服务器只需要满足两个条件：

1. `market-intel` 代码可运行。
2. `MDP_DIR` 指向已 clone 的私有仓库。
3. `DATA_PLATFORM_ROOT` 指向已刷新过的 market-data-platform 数据目录。

如果缺少完整数据湖，晨报仍可读取 `data-snapshots/` 中的跨市场和轻量 TuShare 快照。A 股完整分析、热点筛选和图表会降级或明确失败，避免在 `market-intel` 内临时重造全量下载器。

新机器配置步骤见 [new-machine-setup.md](new-machine-setup.md)。

## 报告生成边界

报告阶段不临时拼接自由文本。每次运行都会先形成可审计的中间产物：

- 新闻：`ai_market_news*.json`（晨报默认写空 payload，不调用 AI 新闻抓取）
- 晨报清单：`morning_manifest.json`
- 晚报清单：`evening_manifest.json`
- 晚报复盘：`evening_review.json`、`evening_review.md`，其中 `market_temperature` 是可审计的确定性解释层
- 图表：`out/a_share_daily/*.png`
- 日间验证归档：`out/a_share_daily/history/evening_review_YYYYMMDD.json` 及对应 Markdown/温度图

这些产物通过契约和测试约束。投递层只消费这些文件，不向 LLM 请求新的事实判断。

晨报入口：

```bash
scripts/morning_pipeline.sh
```

流程：

1. `daily_watch20_delivery.sh` 校验并发送 research-workspace 的 DailyWatch20，失败时不阻塞后续报告。
2. `a_share_daily.d11_h5_shadow_delivery` 只消费 research-workspace 的研究产物。旧 AI 精选入口仅保留显式人工兼容调用，不进入默认调度。
3. 默认写空新闻 JSON，只有 `MORNING_ENABLE_AI_NEWS=1` 时才调用 `fetch_ai_market_news.py`。
4. `a-share-daily morning` 生成机械清单。
5. `a-share-daily morning-report` 根据清单、快照和新闻 `items[]` 渲染 Markdown。
6. `morning_pipeline.sh` 调用 `a_share_daily.delivery.report_delivery` 投递代码化事实材料（`lark-cli` 主通道，Hermes 补发，webhook 文字兜底）。
7. Hermes 可读取同一份 Markdown/清单做点评，点评失败不影响事实材料送达。

晚报入口：

```bash
scripts/evening_pipeline.sh
```

晚报继续复用 `a-share-daily evening/review` 的代码化输出。摘要版晚报由 `a_share_daily.delivery.report_delivery` 消费结构化事实和 `market_temperature` 生成。温度计算不联网、不调用模型，只消费当日聚合值、前 20 个交易日成交额基线和上一份归档中的验证条件。`evening_review.md` 不交给点评流程改写事实。

`evening_pipeline.sh` 生成 `evening_summary.md`、`evening_review.md` 和图表后，用六维市场温度计替换晚间旧情绪图，并归档当日复盘供下一交易日验证。随后由代码投递完整报告，Hermes 负责后续点评和解释。
