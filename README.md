# Market Intel

面向用户的自动化市场情报与投递系统。它抓取全球市场与新闻上下文，消费 `research-workspace` 发布的 A 股策略/研究产物，把事实和版本化 artifact 渲染成日报、晚报、周报、网页看板与飞书消息，并负责投递窗口、幂等、freshness 与故障恢复。

策略计算、因子研究、回测、消融和模型生产不在本仓维护。A 股数据/研究/策略 owner 位于 `research-workspace`；跨仓协作只走公开 CLI 与版本化文件契约。`market-intel` 可以触发 owner 的公开生产入口做同日恢复，但不会复制或维护第二套策略实现。

## 它能产出什么

- 全球市场日报（`dm run`）：海外市场、主题评分、跨市场上下文与新闻事实
- A 股晨报与晚报：消费 DailyWatch20、D11-H5 等已发布策略产物，并组合市场温度、新闻与图表
- 价值/风格周报与决策卡：消费 research-workspace 发布的版本化研究产物
- 静态网页看板（`dm dashboard`）：分数、动作、快照与可选状态面板
- 飞书投递：按受众分群发送，并记录回执、幂等键与恢复状态

## 系统边界

```text
research-workspace
  market-data-platform / alpha-research / portfolio-backtester
  strategy-app / strategy-pipeline / strategy-research / execution
                  │
                  │ public CLI + versioned artifacts
                  ▼
market-intel
  market context → validation → report/render → delivery → operations
```

历史上本仓曾内嵌 `a-share-factor-core`、`hot-sector-screener`、`ai-stock-picker` 三个 submodule。它们已退休并从仓库移除：相关研究能力已经由 research-workspace 的职责仓接管，旧 AI 精选定时产品也已停止生产。

## 快速开始

```bash
uv sync --locked --no-dev

# 全球市场日报（缺密钥时按配置降级）
API_KEYS='{}' uv run dm run --force-score

# 静态网页看板
uv run dm dashboard

# 查看命令
uv run dm --help
uv run marketops --help
uv run a-share-daily --help
```

涉及 A 股正式策略 artifact、数据湖或恢复入口时，部署方需要显式提供 research-workspace 路径：

```bash
export RESEARCH_WORKSPACE_ROOT=/path/to/research-workspace
export MDP_DIR="$RESEARCH_WORKSPACE_ROOT/quant-market-data-platform"
export STRATEGY_PIPELINE_ROOT="$RESEARCH_WORKSPACE_ROOT/strategy-pipeline"
```

这些路径用于调用公开 CLI，不构成源码 import 接口；详见 [跨仓边界契约](docs/boundary-contract.md)。

开发和质量检查：

```bash
uv sync --locked --group dev
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv run python scripts/dev/install_git_hooks.py
```

`market-intel` 的质量门只检查本仓。research-workspace 与其 owner 仓使用各自的质量门，不由本仓跨目录代跑。

## 仓库里有什么

```text
src/
  daily_messenger/       # 全球市场情报、主题评分、日报与 dashboard
  a_share_daily/         # A 股报告组装、正式 artifact 校验、渲染与投递
  a_share_analysis/      # 报告侧分析与已发布研究产物消费
  tushare_jobs/          # 报告专用兼容导出/轻量数据任务；权威数据 owner 在 MDP
  style_replica_bridge/  # 将 owner 回测产物转换为报告 tearsheet
  ops_common/            # 投递窗口、freshness、恢复、环境与通知
config/                  # 报告、评分与 TA 配置
data-snapshots/          # 跨市场与报告兜底快照
docs/                    # 架构、运维、契约与方法说明
scripts/                 # 报告/投递/部署与 owner CLI 桥接入口
```

## 常用命令

```bash
# 全球市场日报
dm run
dm fetch
dm score --force
dm digest
dm dashboard
dm btc report

# A 股报告与部署
uv run a-share-daily doctor --live
uv run a-share-daily morning

# DailyWatch20 正式产物：strategy-pipeline 生产，market-intel 校验并投递
bash scripts/refresh_daily_watch20.sh
uv run python scripts/send_daily_watch20.py --help
```

`refresh_daily_watch20.sh` 的职责是运维恢复桥：检查数据/分钟 freshness，并调用 `strategy-pipeline` 的公开 `strategy watchlist20 ...` 入口。模型、候选池、消融与研究实现仍归 research-workspace。

## 文档导航

- [系统架构](docs/architecture.md)：报告、数据源与运行链路
- [跨仓边界契约](docs/boundary-contract.md)：market-intel / research-workspace 职责与调用规则
- [日内调度](docs/daily-schedule.md)：报告与数据任务时间表
- [运维手册](docs/operations.md)：降级、幂等、恢复与排障
- [数据 owner](docs/data-ownership.md)：MDP 与报告侧数据边界
- [报告分发](docs/report-distribution.md)：受众、消息与回执
- [报告结构](docs/report-structure.md)：Markdown/图片/卡片结构
- [产物契约](docs/contracts.md)：跨模块和跨仓 artifact 契约
- [网页看板](docs/web-dashboard.md)：dashboard 输入与生成
- [测试](docs/testing.md)：本仓测试和质量门
- [主题评分](docs/scoring.md) / [TA 方法](docs/ta-methodology.md)：market-intel 自有分析方法

## 开发与测试

```bash
uv run python project_tools/check_all.py --scope all
uv run pytest
uv run pytest -k contract
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run python project_tools/update_cli_help.py --check
```

Public CI runs the repository quality gates without secrets or production data.
Production scheduling and deployment remain in `quant-intel-deploy`. 本地 pre-push hook 只管理 `market-intel` 根仓：

```bash
uv run python scripts/dev/install_git_hooks.py
uv run python scripts/dev/install_git_hooks.py --check
```

已合并分支的删除使用 `project_tools/cleanup_merged_branches.py`。它会先通过 `gh` 确认
PR 已合并，只有提供 `--yes` 才执行删除；`main`、tag 和未合并分支会被拒绝。

## 新手须知

- 报告产物写入 `out/`，运行状态与投递回执写入 `state/`。
- 缺少可选资讯源时按配置降级；正式策略 artifact 的日期/契约不满足时则 fail closed。
- market-intel 不因报告需求复制研究模型；缺少研究产物时应修复 research-workspace owner 或通过其公开生产入口恢复。
- 报告和技术分析仅用于研究与信息整理，不构成投资建议。
