# 跨仓边界契约

本文件是 [data-ownership.md](data-ownership.md) 与 [contracts.md](contracts.md) 的补充，专门收口
源码与路径耦合这一项。背景见 2026-07-29 的 `research-workspace` 与 `market-intel` 整合评估报告：
两个仓库应继续保持独立，协作只走公开 CLI 与版本化文件契约，仓库路径不得成为正式接口。

## 1. 边界总则

- `market-intel` 与 `research-workspace`（及其子模块）是两个生命周期不同的独立系统：
  研究侧强调版本锁定、复现与审计，情报侧强调每日调度、联网抓取、投递时效。
- 双方不直接 import 对方业务源码。跨仓协作只通过：
  - 已安装的公开命令（`marketdata ...`、`strategy ...`、`marketops ...`、`aipick ...`）
  - 版本化文件产物（`watchlist_20`、`selection_receipt`、`signals.parquet`、`news_heat` 等，见 `contracts.md`）。
- 仓库路径不当作接口。任何脚本、模块都不得以相邻仓库的固定目录布局（如
  `$HOME/code/research-workspace/...`）作为功能依赖。

## 2. 路径耦合禁令（收口项）

下列写法一律视为违规，应改为环境变量 + 公开 CLI：

| 违规写法 | 正确写法 |
|---|---|
| `Path.home() / "code" / "research-workspace" / "market-data-platform"` | 读 `DATA_PLATFORM_ROOT`（数据湖）或 `MDP_DIR`（代码仓），二者均由部署方显式设置 |
| `cd "$STRATEGY_PIPELINE_ROOT" && uv run strategy ...` | `uv run --project "$STRATEGY_PIPELINE_ROOT" strategy ...`（不切换工作目录） |
| 默认兜底写死 `$HOME/code/...` | 默认不兜底。缺失则报错退出，由部署方通过环境变量提供 |

### 已收口示范

`src/ops_common/env.py` 的 `_env_paths_to_try()` 原先无条件追加
`~/code/research-workspace/market-data-platform` 作为 `.env` 搜索根。现已改为：
仅当显式设置 `MDP_FALLBACK_ROOT` 时才追加该路径，正式接口为 `DATA_PLATFORM_ROOT`。
这意味着未配置的新部署会明确报错，不再隐式依赖固定目录结构。

### scripts / systemd / windows（本批次已完成收口）

- `scripts/*.sh`（morning/evening/publish/refresh_tushare_daily/weekly_recap/morning_product_supervisor/refresh_tushare_report_datasets）— `MDP_DIR` 默认去掉并 require，冗余字面 `.env.local` 改为引用 `$MDP_DIR`
- `scripts/refresh_daily_watch20.sh`：只通过 `STRATEGY_PIPELINE_ROOT` 和 `MDP_DIR` 调用公开 producer CLI；news heat 缺失时继续运行，不在本仓重建。
- `scripts/daily_watch20_delivery.sh`：只校验 research-workspace 产出的 DailyWatch20 artifact，再调用本仓渲染/投递入口。
- `scripts/hotsector_research_handoff.sh`、`scripts/send_hotsector_client_preview.py`：仅保留指向 DailyWatch20 的兼容壳，不再启动历史 hotsector owner。
- `scripts/windows/common.ps1`：`MDP_DIR` 默认去掉，未设则派生或报错
- `scripts/setup_cron.sh`：安装时把
  `RESEARCH_WORKSPACE_ROOT`/`MDP_DIR`/`STRATEGY_PIPELINE_ROOT` 写入权限为 `0600` 的
  部署环境文件。systemd 通过 `EnvironmentFile=` 加载，Hermes 三个入口在边界检查前
  source，同一部署配置覆盖两类调度器
- 依赖跨仓路径的 systemd service（包括 DailyWatch20 producer、morning supervisor 与
  TuShare 刷新）— 统一加载上述部署环境文件。service 模板不再
  自行持有路径默认值

### src Python（已完成收口）

- `src/a_share_daily/deploy_check.py`、`tushare_credentials.py` 只接受显式 `MDP_DIR`
- DailyWatch20 分钟完整性由 `src/a_share_daily/daily_watch20_raw_completeness.py` 负责；
  因子、Hermite、walk-forward、OOS 和消融实现均由 research-workspace owner 负责。
- `scripts/setup_cron.sh` 要求显式 `RESEARCH_WORKSPACE_ROOT`，不再提供
  `$HOME/code/...` 默认值。

仓库扫描与定点测试共同约束上述入口，不再把开发机目录结构当部署契约。

## 3. 重复实现收口

`src/a_share_analysis/style/` 曾与 `research-workspace/src/style_factors/` 同源重复（因子计算、回测、OLS 归因、图表、报告）。按评估报告职责划分：

- 因子定义与计算 → `alpha-research`
- 回测与归因 → `portfolio-backtester`
- 运行与产物发布 → `strategy-pipeline`
- 报告渲染与飞书投递 → `market-intel`

### style 重复实现收口状态

`src/a_share_analysis/style/` 整包（含 `data.py`、`attribution.py`、`factor_calc.py`、`factor_backtest.py`、`charts.py`、`report.py`）已于 2026-07-30 从本仓移除。该包原本是 `research-workspace/src/style_factors` 的冻结副本，且仅有测试引用，删除后不影响任何生产代码。

消费侧仍由 `src/a_share_analysis/style_analysis.py` 承担，它只读消费版本化产物：

- 解析 `$DATA_PLATFORM_ROOT/strategy_outputs/style-factors/latest.txt`
- 通过 `research_contracts` 校验 ArtifactEnvelopeV2、SHA-256、文件大小与 lineage
- 复制完整 owner 产物并写 `consumption_receipt.json`。

`market-intel` 已通过安装依赖锁定 `research-contracts` 的明确 Git 提交，契约校验不再是本仓复制的一套实现。

同理 `src/tushare_jobs/` 中与 `market-data-platform` 数据湖重复的下载任务（如 `stock_st`、`index_weight`、`listed_company` 部分字段）应逐步迁回其唯一 owner。`market-intel` 仅保留报告专用轻量快照（`lightweight_snapshot.py`）与跨市场数据。

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
MDP 现为这些数据集的权威 owner。market-intel 消费
`<DATA_PLATFORM_ROOT>/assets/tushare/a_share/<dataset>/a_share_all_<dataset>_latest.parquet`
及同名 `.receipt.json`。
详细映射见 `docs/data-ownership.md` 的「`tushare_jobs` 迁移状态」一节。

2026-07-30 最终切换：上述消费者采用 fail-closed 策略。缺少资产/receipt、schema 不匹配、
SHA-256 不匹配、行数不符或请求切片不存在时明确失败，不会回退 TuShare 自抓。
`force_full_refresh` 也会提示改用 MDP 的公开 CLI。一致性脚本仍可审计历史兼容文件，但不再控制
是否回退。
