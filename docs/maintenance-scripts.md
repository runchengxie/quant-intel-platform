# 维护脚本与实验代码边界

本仓库包含正式运行入口、低频运维命令、本地诊断脚本和实验工具。团队维护时应先确认代码属于哪一类，再决定测试、发布和告警要求。

## 正式入口

| 入口 | 用途 | 本地调度/质量门 | 质量要求 |
|------|------|---------|----------|
| `dm` | 日报 ETL、评分、渲染、BTC 辅助命令 | 本机报告任务，pre-push root 门禁 | Ruff、ruff format、ty、pytest 加 coverage、契约测试 |
| `marketops` | TuShare 数据任务 | Windows Task Scheduler / Linux systemd，pre-push root 门禁 | Ruff、ruff format、ty、TuShare 单元测试 |
| `a-share-daily` | A 股晨报、晚报、图表和飞书事实层投递 | `scripts/morning_pipeline.sh`、`scripts/evening_pipeline.sh`、`scripts/windows/*.ps1`、Hermes 定时任务 | Ruff、ty、pytest 重点测试，ty 覆盖全部 `src/` 源码 |

## 低频运维命令

| 命令 | 用途 | 注意事项 |
|------|------|----------|
| `dm btc init-history` | 一次性或低频下载 Binance 历史 K 线并合并 Parquet | 网络和磁盘成本较高。运行前确认 `out/btc/` 或自定义输出目录 |
| `marketops tushare stock-st backfill` | ST 历史回填 | 消耗 TuShare 配额。建议指定日期范围 |
| `marketops tushare listed-company backfill --consolidate` | 上市公司数据全量刷新 | 消耗 TuShare 配额。关注断点续跑和输出格式 |
| `scripts/refresh_tushare_report_datasets.sh YYYYMMDD` | 补抓日报主题、资金流、概念和涨跌停关键数据，题材映射与四项事件确认源默认滚动回补最近 5 个交易日 | 默认跳过。设置 `A_SHARE_ENABLE_TUSHARE_PREMIUM=1` 后才请求接口，staging 校验失败时保留 last-known-good 并写负回执 |
| `scripts/windows/install_scheduled_tasks.ps1` | 注册 Windows 晨报和晚报定时任务 | 默认 07:00 和 19:00，选股预览内嵌在晨报任务。改时间后用 `-Force` 重新注册 |

## 定时任务与诊断脚本

以下脚本由本机调度（Windows Task Scheduler、Linux systemd/cron、Hermes 定时任务）或手动触发，属于运行链路的一环，但未列入正式入口或低频运维命令。

| 脚本 | 用途 |
|------|------|
| `scripts/morning_pipeline.sh` | 晨报流水线薄包装：自动探测最新交易日、预抓新闻与跨市场数据，调用 `a-share-daily morning` |
| `scripts/evening_pipeline.sh` | 晚报流水线：数据刷新、图表、盘后点评与美股盘前预览，单一 cron 入口（19:00 CST 工作日） |
| `scripts/refresh_tushare_daily.sh` | 亚洲市场日频数据刷新 systemd timer 入口（15:30 CST 后），A 股与日韩市场的当日唯一定时抓取 |
| `scripts/publish_a_share_current.sh` | TuShare 原始刷新后发布 A 股当前契约：构建并校验 daily_clean、构建并校验股票池、修复累计原始清单、晋升产物 |
| `scripts/local_fetch_cross_market.sh` | 本机跨市场数据抓取 Linux cron 入口（05:00 CST 之后、07:00 Hermes 之前），三层补抓策略的 Layer 2 |
| `scripts/refresh_weekly_style_factors.sh` | 周六 08:15 风格因子兼容入口：转调用 research-workspace owner，保留调度与回执路径兼容 |
| `scripts/weekly_recap.sh` | 周报 cron 入口：价值因子区制周报与基于晨报的市场周报 |
| `scripts/morning_product_supervisor.sh` | 加载与晨报相同的凭证与目标，监督 DailyWatch20、D11-H5 和报告投递 |
| `scripts/daily_watch20_delivery.sh` | 校验 research-workspace 的 DailyWatch20 artifact 并调用本仓投递器 |
| `scripts/ensure_hermes_gateway.sh` | 确保 systemd 托管的 Hermes 网关处于活跃状态，健康实例不重启 |
| `scripts/fetch_ai_market_news.py` | 结构化 AI 市场新闻抓取的薄 CLI 包装 |
| `scripts/refresh_a_share_index_daily.py` | A 股指数日频数据刷新脚本 |
| `scripts/send_daily_watch20.py` | 向配置目标发送已验证的 DailyWatch20 artifact |

### 新鲜度看门狗

这些脚本独立校验各产物的新鲜度，通常由定时任务在投递前或单独诊断时调用，配套同名 `.sh` 包装负责定时触发。

| 脚本 | 校验对象 |
|------|----------|
| `scripts/check_daily_watch20_producer_freshness.py` | DailyWatch20 生产者及其发布产物的新鲜度（内部运维自检，依赖 supervisor 的 systemd failed 状态作为上游升级信号） |
| `scripts/check_index_daily_freshness.py` | A 股 index_daily 快照的新鲜度 |

## `project_tools/`

| 脚本 | 使用者 | 是否 pre-push 使用 | 作用 |
|------|--------|--------------|------|
| `check_all.py` | 开发者、本地钩子 | 是，唯一质量命令源 | 只检查 market-intel 根仓，并覆盖 Python、shell/PowerShell 脚本 |
| `pre_push_guard.py` | 本地钩子 | 是 | 只保护 market-intel 根仓的分支、clean HEAD 和本地质量门，失败阻止 push |
| `update_cli_help.py` | 开发者、本地钩子 | 是，root 质量门调用 | 防止 CLI 文档漂移 |
| `scripts/dev/install_git_hooks.py` | 开发者 | 否，负责安装钩子 | 幂等安装、检查或卸载 market-intel 根仓 managed pre-push 钩子 |

新增脚本应在上表登记，并明确：

- 是否被本地 pre-push 钩子或生产调度调用
- 需要哪些环境变量或 secret
- 是否会访问网络、消耗配额或写入大文件
- 失败是否应阻塞发布

## 兼容入口与遗留清单

| 入口 | 状态 | Owner | 处置策略 |
|------|------|-------|----------|
| `scripts/evening_review_pipeline.py` | 旧定时任务兼容入口 | 运维脚本 | 新部署改用 `scripts/evening_pipeline.sh` 或 `scripts/windows/evening_pipeline.ps1`，该脚本仍有 `tests/test_evening_review_pipeline_script.py` 引用，暂保留 |
| `src/ops_common/notify_email.py` | 暂无调用点 | `marketops` 运维 | 全仓已无引用，若重新启用邮件告警需先补测试和文档，否则下次清理可直接删除 |

`src/a_share_analysis/post_market_review.py` 原为盘后点评兼容 wrapper，其 canonical 实现已迁到 `a_share_daily.review`，外部调度全部走 `a-share-daily evening/review`，该 wrapper 已无引用并删除。

## A 股日报 CLI：`a_share_daily`

`src/a_share_daily/` 承担晨报和晚报的正式生成、图表输出和飞书事实层投递。它依赖本机 `DATA_PLATFORM_ROOT`、research-workspace 的公开 CLI/artifact 和 `data-snapshots/` 快照。当前已有投递、新闻契约、CLI 冒烟、缺数据边界和部署检查测试。

已落地：

1. `a-share-daily doctor` 可检查脚本权限、`market-data-platform` 仓库、数据湖、latest 快照、AI key、飞书投递目标、`lark-cli`。`--live` 在 Windows 上额外检查 Task Scheduler，在 Linux 上额外检查 systemd timer，并同时检查 Hermes 定时任务。
2. `refresh_tushare_report_datasets.sh` 负责补抓主题、资金流、概念和涨跌停关键数据。这些接口默认关闭，设置 `A_SHARE_ENABLE_TUSHARE_PREMIUM=1` 后才请求。DailyWatch20 的候选池、研究计算和正式产物均由 research-workspace 负责。本仓只校验、渲染和投递已发布产物。
3. 根项目 `ty check` 已覆盖全部 `src/` 源码，包括日报 CLI、流水线、data、review、cross-market、charts 与投递。
4. 流水线层测试已覆盖缺日频核心数据、高权限 TuShare 默认跳过、缺可选 owner artifact 和缺 `moneyflow_ths` 时的返回契约与占位图行为。

后续维护重点：

1. 新增源码必须保持在 ty 全量检查范围内，不得通过扩大排除目录绕过类型错误。
2. 继续拆分 `report_delivery` 和剩余长流程 helper，根项目已不再保留 `C901` 历史豁免，后续新增复杂函数应直接被 Ruff 拦截。
3. 继续补充流水线层测试，覆盖缺 owner artifact、缺 data lake、跨市场快照过期和 TuShare 高权限接口空结果。
4. 保持 `a-share-daily` 的模块边界清晰：数据读取、图表、文本渲染、投递各自独立，避免把推送逻辑写进数据抓取阶段。

当前维护边界：

1. `market-data-platform` 保持为独立仓库，`market-intel` 通过 `DATA_PLATFORM_ROOT` 只读使用。
2. 日报只消费带来源、URL 和发布时间的结构化 `items[]`，新闻自由文本不直接进入正文。
3. Hermes 继续负责后续点评和解释，事实报告由代码生成和投递。
