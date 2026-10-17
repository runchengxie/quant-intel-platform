# 跨仓边界契约

[English page](boundary-contract.en.md)

本文件是 [data-ownership.md](data-ownership.md) 与 [contracts.md](contracts.md) 的补充，专门收口
源码与路径耦合这一项。背景见 2026-07-29 的旧工作区与 `market-intel` 整合评估报告：
两个仓库应继续保持独立，协作只走公开 CLI 与版本化文件契约，仓库路径不得成为正式接口。

## 1. 边界总则

- `quant-intel-platform` 与 `quant-research`、`quant-platform`、`quant-market-data-platform` 是职责不同的独立系统：
  研究侧强调版本锁定、复现与审计，情报侧强调每日调度、联网抓取、投递时效。
- 双方不直接 import 对方业务源码。跨仓协作只通过：
  - 已安装的公开命令（`marketdata ...`、`strategy ...`、`daily-watch20-owner ...`、`marketops ...`）
  - 版本化文件产物（`watchlist_20`、`selection_receipt`、`signals.parquet`、`news_heat` 等，见 `contracts.md`）。
- 已退役的 AI 精选产品不能通过旧 CLI 或 artifact 名称重新成为生产默认。
- 仓库路径不当作接口。任何脚本、模块都不得以相邻仓库的固定目录布局（如
  任意开发机固定路径）作为功能依赖。

## 2. 路径耦合禁令（收口项）

下列写法一律视为违规，应改为环境变量 + 公开 CLI：

| 违规写法 | 正确写法 |
|---|---|
| 任意开发机固定的仓库路径 | 读 `DATA_PLATFORM_ROOT`（数据湖）或 `MDP_DIR`（代码仓），二者均由部署方显式设置 |
| `cd "$QUANT_RESEARCH_ROOT" && uv run strategy ...` | `uv run --project "$QUANT_RESEARCH_ROOT" strategy ...`（不切换工作目录） |
| 默认兜底写死 `$HOME/code/...` | 默认不兜底。缺失则报错退出，由部署方通过环境变量提供 |

### 已收口示范

`src/ops_common/env.py` 的 `_env_paths_to_try()` 原先无条件追加
固定仓库路径作为 `.env` 搜索根。现已改为：
仅当显式设置 `MDP_FALLBACK_ROOT` 时才追加该路径，正式接口为 `DATA_PLATFORM_ROOT`。
这意味着未配置的新部署会明确报错，不再隐式依赖固定目录结构。

### 脚本和调度器

生产桥接脚本、Windows 入口和调度模板由 `quant-intel-deploy` 维护，不在本仓提供。当前 `daily-watch20-producer.timer` 调用 Deploy 的 `scripts/refresh_daily_watch20_quant_research.sh`，由已安装的 `daily-watch20-runtime` 发布产物，再由 `daily-watch20-owner freshness` 校验。`scripts/refresh_daily_watch20.sh` 保留为旧版有界回滚入口，不是该 timer 的 producer。两条路径都通过显式配置的 `QUANT_RESEARCH_ROOT` 调用已安装的 owner 命令。市场数据恢复通过 `MDP_DIR` 下已安装的 `marketdata` CLI 执行。`installed_owner` 在启动命令前清除 `PYTHONPATH` 和 `PYTHONHOME`。报告生成和投递消费 owner 产物，不导入相邻源码。

Deploy 的 provider 任务通过 `marketdata config run --config "$DATA_PLATFORM_CONFIG" -- COMMAND ARGS...` 加载 owner 管理的供应商凭据，不 source JSON，也不把 provider `.env.local` 作为权威凭据库。其他凭据 owner 保留各自配置。

### Python 源码（已完成收口）

- `src/a_share_daily/deploy_check.py`、`tushare_credentials.py` 只接受显式 `MDP_DIR`
- DailyWatch20 分钟完整性由 `src/a_share_daily/daily_watch20_raw_completeness.py` 负责。
  因子、Hermite、walk-forward、OOS 和消融实现均由 `quant-research` owner 负责。
- 部署调度配置由 `quant-intel-deploy` 维护。

仓库扫描与定点测试共同约束上述入口，不再把开发机目录结构当部署契约。

## 3. 重复实现收口

`src/a_share_analysis/style/` 曾与 `research-workspace/src/style_factors/` 同源重复（因子计算、回测、OLS 归因、图表、报告）。按评估报告职责划分：

- 私有因子定义与策略计算 → `quant-research`
- 通用回测、执行模拟与归因 → `quant-platform`
- 通用回测任务状态、worker 和结果发布 → `quant-backtest-runtime`
- 策略编排与产物发布 → `quant-research`
- 报告渲染与飞书投递 → `quant-intel-platform`

旧仓库名称只描述迁移历史。既有 Python 命名空间、CLI 名称、配置键和 artifact 标识仍是兼容接口，不是当前独立 owner。

### style 重复实现收口状态

`src/a_share_analysis/style/` 整包（含 `data.py`、`attribution.py`、`factor_calc.py`、`factor_backtest.py`、`charts.py`、`report.py`）已于 2026-07-30 从本仓移除。该包原本是 `research-workspace/src/style_factors` 的冻结副本，且仅有测试引用，删除后不影响任何生产代码。

消费侧仍由 `src/a_share_analysis/style_analysis.py` 承担，它只读消费版本化产物：

- 解析 `$DATA_PLATFORM_ROOT/strategy_outputs/style-factors/latest.txt`
- 通过 `research_contracts` 校验 ArtifactEnvelopeV2、SHA-256、文件大小与 lineage
- 复制完整 owner 产物并写 `consumption_receipt.json`。

本分发包包含 `research_contracts` 兼容包。`pyproject.toml` 没有声明单独通过 Git 提交锁定的 `research-contracts` 依赖。

同理 `src/tushare_jobs/` 中与 `quant-market-data-platform` 数据湖重复的下载任务（如 `stock_st`、`index_weight`、`listed_company` 部分字段）应逐步迁回其唯一 owner。`quant-intel-platform` 仅保留报告专用轻量快照（`lightweight_snapshot.py`）与跨市场数据。

### tushare_jobs 重叠任务收口状态

重叠模块已经收口为兼容导出器：

- `stock_st.py`：从 MDP `stock_st` 资产导出请求日期，不再调用 TuShare
- `listed_company.py`：`stock_company`、`stk_managers`、`share_float` 从 MDP 资产筛选
  仅报告专用的轻量 `stock_basic` 快照仍允许直接刷新
- `index_weight.py`：从 MDP `index_weight` / `index_weight_daily` 成对导出，不再下载或日频展开
- `lightweight_snapshot.py`、跨市场数据：保留（报告专用离岸/备份 JSON）

2026-07-30 更新：MDP 已完成等价下载能力（历史实现提交为 `4535cd7`，当前代码已进入
`main`）。实现位于 `providers/tushare_a_share_reference.py`，包含
stock_st、index_weight、index_weight_daily、stock_company、stk_managers、share_float
的 DatasetSpec、download、drift_weight 展开与 publish，并注册到
`marketdata tushare download-a-share-reference` 等子命令、registry 与资产路径。
MDP 现为这些数据集的权威 owner。quant-intel-platform 消费
`<DATA_PLATFORM_ROOT>/assets/tushare/a_share/<dataset>/a_share_all_<dataset>_latest.parquet`
及同名 `.receipt.json`。
详细映射见 `docs/data-ownership.md` 的「`tushare_jobs` 迁移状态」一节。

2026-07-30 最终切换：上述消费者采用 fail-closed 策略。缺少资产/receipt、schema 不匹配、
SHA-256 不匹配、行数不符或请求切片不存在时明确失败，不会回退 TuShare 自抓。
`force_full_refresh` 也会提示改用 MDP 的公开 CLI。一致性脚本仍可审计历史兼容文件，但不再控制
是否回退。


## Owner JSON 配置

供应商任务通过已合并、已安装的 owner CLI 启动：
`marketdata config run --config "$DATA_PLATFORM_CONFIG" -- COMMAND ARGS...`。
所选私有 JSON 按数据 owner 的版本化契约配置。版本 1 可以直接保存供应商凭据，版本 2 引用 owner 管理的凭据库和独立任务 JSON。消费者不导入 owner loader，也不解析供应商 JSON。doctor 只检查所选文件的元数据和继承的凭据状态。选择 JSON 后，排除旧 provider env 文件和项目 env 中的 provider 条目；其他凭据 owner 的配置仍保留。JSON 内容由固定版本 owner 的 `config check` 验证，doctor 应通过 `config run` 启动。
