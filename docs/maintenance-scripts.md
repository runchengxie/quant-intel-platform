[English page](maintenance-scripts.en.md)

# 维护脚本与实验代码边界

本仓库提供正式 CLI、本地诊断和研究工具。生产调度、桥接脚本和恢复入口由 `quant-intel-deploy` 维护。

## 正式入口

| 入口 | 用途 | 本地调度/质量门 | 质量要求 |
|------|------|---------|----------|
| `dm` | 日报 ETL、评分、渲染、BTC 辅助命令 | 本机报告任务，PR/main CI 门禁 | Ruff、ruff format、ty、pytest 加 coverage、契约测试 |
| `marketops` | TuShare 数据任务 | 由部署调度调用已安装 CLI；PR/main CI 门禁 | Ruff、ruff format、ty、TuShare 单元测试 |
| `a-share-daily` | A 股晨报、晚报、图表和飞书事实层投递 | 部署侧 Task Scheduler、systemd、cron 或 Hermes 调度调用已安装 CLI | Ruff、ty、pytest 重点测试，ty 覆盖全部 `src/` 源码 |

## 低频运维命令

| 命令 | 用途 | 注意事项 |
|------|------|----------|
| `dm btc init-history` | 一次性或低频下载 Binance 历史 K 线并合并 Parquet | 网络和磁盘成本较高。运行前确认 `out/btc/` 或自定义输出目录 |
| `marketops tushare stock-st backfill` | ST 历史回填 | 消耗 TuShare 配额。建议指定日期范围 |
| `marketops tushare listed-company backfill --consolidate` | 上市公司数据全量刷新 | 消耗 TuShare 配额。关注断点续跑和输出格式 |

## 由 Deploy 维护的脚本与调度

生产 shell/PowerShell 桥接脚本、Task Scheduler/systemd/cron/Hermes 定时定义、新鲜度看门狗和恢复命令由 `quant-intel-deploy` 维护，不属于本仓库。这些脚本调用已安装的 `marketops`、`a-share-daily` CLI，或消费带版本的 owner artifact。公开应用代码和对应测试仍由本仓维护。

## `project_tools/`

| 脚本 | 使用者 | 是否由 CI 调用 | 作用 |
|------|--------|--------------|------|
| `check_all.py` | 开发者、GitHub Actions | 是，完整门禁入口 | 运行 Python、shell、PowerShell 和 JavaScript 检查 |
| `update_cli_help.py` | 开发者、GitHub Actions | 是，由完整质量门禁调用 | 防止 CLI 文档漂移 |

新增脚本应在上表登记，并明确：

- 是否被 CI 或生产调度调用
- 需要哪些环境变量或 secret
- 是否会访问网络、消耗配额或写入大文件
- 失败是否应阻塞发布

## 兼容入口与遗留清单

| 入口 | 状态 | Owner | 处置策略 |
|------|------|-------|----------|
| `src/ops_common/notify_email.py` | 暂无调用点 | `marketops` 运维 | 全仓已无引用，若重新启用邮件告警需先补测试和文档，否则下次清理可直接删除 |

`src/a_share_analysis/post_market_review.py` 原为盘后点评兼容 wrapper，其 canonical 实现已迁到 `a_share_daily.review`，外部调度全部走 `a-share-daily evening/review`，该 wrapper 已无引用并删除。

## A 股日报 CLI：`a_share_daily`

`src/a_share_daily/` 承担晨报和晚报的正式生成、图表输出和飞书事实层投递。它依赖本机 `DATA_PLATFORM_ROOT`、owner 的公开 CLI/artifact 和 `data-snapshots/` 快照。当前已有投递、新闻契约、CLI 冒烟、缺数据边界和部署检查测试。

已落地：

1. `a-share-daily doctor` 可检查脚本权限、`quant-market-data-platform` 仓库、数据湖、latest 快照、AI key、飞书投递目标、`lark-cli`。`--live` 在 Windows 上额外检查 Task Scheduler，在 Linux 上额外检查 systemd timer，并同时检查 Hermes 定时任务。
2. 部署侧刷新任务可补抓主题、资金流、概念和涨跌停数据。这些接口默认关闭，设置 `A_SHARE_ENABLE_TUSHARE_PREMIUM=1` 后才请求。DailyWatch20 的候选池、研究计算和正式产物均由 `quant-research` / `strategy-pipeline` 负责。本仓只校验、渲染和投递已发布产物。
3. 根项目 `ty check` 已覆盖全部 `src/` 源码，包括日报 CLI、流水线、data、review、cross-market、charts 与投递。
4. 流水线层测试已覆盖缺日频核心数据、高权限 TuShare 默认跳过、缺可选 owner artifact 和缺 `moneyflow_ths` 时的返回契约与占位图行为。

后续维护重点：

1. 新增源码必须保持在 ty 全量检查范围内，不得通过扩大排除目录绕过类型错误。
2. 继续拆分 `report_delivery` 和剩余长流程 helper，根项目已不再保留 `C901` 历史豁免，后续新增复杂函数应直接被 Ruff 拦截。
3. 继续补充流水线层测试，覆盖缺 owner artifact、缺 data lake、跨市场快照过期和 TuShare 高权限接口空结果。
4. 保持 `a-share-daily` 的模块边界清晰：数据读取、图表、文本渲染、投递各自独立，避免把推送逻辑写进数据抓取阶段。

当前维护边界：

1. `quant-market-data-platform` 保持为独立仓库，`market-intel` 通过 `DATA_PLATFORM_ROOT` 只读使用。
2. 日报只消费带来源、URL 和发布时间的结构化 `items[]`，新闻自由文本不直接进入正文。
3. Hermes 继续负责后续点评和解释，事实报告由代码生成和投递。
