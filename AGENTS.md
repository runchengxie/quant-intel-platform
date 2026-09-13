# 仓库开发指南

## 职责边界

`market-intel` 是市场情报、报告、投递和运行保障系统。A 股策略研究、因子计算、模型训练、回测、消融与策略 artifact 生产由 `research-workspace` 的职责仓维护。

跨仓协作只允许两类接口：

- 公开 CLI，例如 `marketdata ...`、`strategy watchlist20 ...`
- 版本化文件 artifact / receipt

不得从 `market-intel` import research-workspace 的业务源码，也不得把研究实现复制回本仓。报告侧可以验证、消费和渲染 owner artifact；运维恢复可以调用 owner 的公开 CLI，但不能维护第二套模型逻辑。

历史 `a-share-factor-core`、`hot-sector-screener`、`ai-stock-picker` submodule 已退休并从本仓移除。旧 AI 精选产品不得通过兼容入口重新变成生产默认。

## 项目结构

运行时代码位于 `src/`：

- `daily_messenger/`：全球市场 ETL、主题评分、日报、技术分析、Dashboard 与飞书工具；CLI 为 `dm`。
- `a_share_daily/`：A 股晨晚报、正式策略 artifact 校验、报告组装、图表和投递；CLI 为 `a-share-daily`。
- `a_share_analysis/`：报告侧分析和已发布研究产物的消费适配。新研究算法不得继续放入这里。
- `tushare_jobs/`：报告专用轻量任务与兼容导出；权威 A 股数据 owner 为 research-workspace 的 `market-data-platform`。
- `style_replica_bridge/`：将 owner 回测产物转换为报告 tearsheet。
- `ops_common/`：环境、投递窗口、freshness、恢复和通知。

配置在 `config/`，运行状态在 `state/`，报告产物在 `out/`，文档在 `docs/`，本地质量工具在 `project_tools/`。

## 开发命令

```bash
uv sync --locked --group dev
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
uv run pytest -k contract
uv run python project_tools/update_cli_help.py --check
```

完整本仓门禁：

```bash
uv run python project_tools/check_all.py --scope all
```

首次克隆或质量工具更新后：

```bash
uv run python scripts/dev/install_git_hooks.py
uv run python scripts/dev/install_git_hooks.py --check
```

pre-push hook 只管理 `market-intel` 根仓。research-workspace 和各 owner 仓运行它们自己的门禁。本仓禁止重新增加“遍历相邻 repo 代跑检查”的逻辑。

## 生产与恢复入口

常用入口：

```bash
uv run dm run
uv run a-share-daily morning
uv run a-share-daily doctor --live
bash scripts/refresh_tushare_report_datasets.sh YYYYMMDD
bash scripts/refresh_daily_watch20.sh
```

`refresh_daily_watch20.sh` 是运维桥，不是模型 owner：它处理必要的 freshness / 分钟数据恢复后调用 `strategy-pipeline` 的公开 `strategy watchlist20 run/freshness`。DailyWatch20 的候选池、特征、训练和消融逻辑必须留在 research-workspace。

定时任务安装：

```bash
export RESEARCH_WORKSPACE_ROOT=/path/to/research-workspace
bash scripts/setup_cron.sh --layer2
bash scripts/setup_cron.sh --layer3
```

`setup_cron.sh` 会主动卸载本仓历史研究 timer，包括 factor-observation、DW20 ablation、hotsector standalone 和 legacy AI freshness unit。

## 代码放置规则

新增代码前先判断 owner：

- 市场资讯抓取、报告内容、渲染、Dashboard、飞书、投递回执、报告窗口、故障恢复 → `market-intel`
- 市场数据权威资产 → `market-data-platform`
- 特征/模型/统计推断 → `alpha-research`
- 回测、成本、容量、组合与历史成交模拟 → `portfolio-backtester`
- 策略专用纯计算与冻结研究合同 → `strategy-app`
- 策略运行、发布门禁、原子 artifact 发布 → `strategy-pipeline`
- 策略身份、生命周期、研究规格和证据导航 → `strategy-research`
- 实盘/模拟执行与券商审计 → `quant-execution-engine`

当 market-intel 需要研究侧能力时，优先补 owner API/CLI 或 artifact 契约。不要以“暂时方便”为理由在本仓再实现一次。

## 测试原则

测试应覆盖：

- ETL、评分、报告和降级路径
- artifact 日期/schema/hash 的 fail-closed 校验
- DailyWatch20 等正式 owner artifact 的消费与投递
- 飞书幂等、受众隔离和 delivery receipt
- scheduler / recovery 的状态机与旧 unit 清理
- Dashboard 和报告渲染回归

研究算法的 OOS、ablation、walk-forward、Hermite 等测试归 research-workspace owner，本仓不保留镜像测试。

## 提交与 PR

- 从 `origin/main` 建独立 worktree，分支仅使用 `feat/*`、`fix/*`、`hotfix/*`、`release/*`。
- `main` 只接受合并后的 PR，不直接修改或 push。
- Commit 聚焦单一目的，标题尽量控制在 72 字符以内。
- 跨仓 owner 变更按 provider → consumer → superproject gitlink 的顺序合并；不得让 market-intel 临时依赖未合并的本地源码路径。
- 涉及报告版面、卡片或权重时附代表性产物；涉及契约时同步文档和 contract tests。
- 无法真实执行本地门禁时，PR 必须保持 Draft，并明确列出未验证项，禁止写“tests passed”之类的祈祷式声明。

## 配置与密钥

凭证只放环境变量、`.env.local` 或对应 owner 规定的私有位置。不要提交真实密钥。跨仓代码路径必须由部署环境显式提供，例如：

```bash
RESEARCH_WORKSPACE_ROOT=/path/to/research-workspace
MDP_DIR=$RESEARCH_WORKSPACE_ROOT/quant-market-data-platform
STRATEGY_PIPELINE_ROOT=$RESEARCH_WORKSPACE_ROOT/strategy-pipeline
```

仓库路径只用于启动公开 CLI，不是 Python API。

## GitHub Actions 策略

本仓在 PR 和 `main` 推送时运行轻量 GitHub Actions 质量门禁，不读取真实市场数据、不调用飞书或券商。完整生产检查仍由本地 pre-push 和手动运行负责。历史快照 workflow 保留为 `.disabled` 文件，不得在 CI 中重新启用真实数据抓取和自动提交。

public framework 的 lint、类型检查、离线测试和构建应优先放在本仓运行。私有部署仓库的 GitHub Actions 默认关闭，以避免消耗有限的 private-repository minutes；private 部署变更必须先通过本地 `uv sync --locked`、部署 smoke tests 和调度模板检查。只有在 production shadow/canary 或正式切换前确实需要时，才临时启用 private workflow，并在任务完成后关闭。

## Worktree-first 目录规范

开发和实验使用 `/home/richard/code/.worktrees/` 下的独立 worktree。日报、周报、投递和恢复
任务必须使用稳定的生产检出路径，不得依赖会被清理的开发 worktree。当前生产路径由部署环境
通过 `MARKET_INTEL_ROOT`、`RESEARCH_WORKSPACE_ROOT`、`MDP_DIR` 和 `STRATEGY_PIPELINE_ROOT`
显式提供。运行数据、报告产物、receipt、缓存和日志放在仓库外。路径迁移后必须 reload
systemd，并用对应入口做 smoke test。

## 多 agent 强制协作流程

以下流程适用于每个任务和每个 agent，包括纯文档修改。每个 agent 必须使用自己的独立
worktree 和任务分支，明确文件与仓库责任范围，不得共用检出目录或分支进行并行写入。
开始前检查工作区状态和 origin 身份。同一远端的多个旧检出只更新一次，不把旧检出当作
另一份独立实现，也不擅自更新其他工作区或父仓库的 gitlink。

1. 先运行 `git fetch origin`，再从本次获取的 `origin/main` 创建任务分支和独立
   worktree。worktree 放在仓库外的 `/home/richard/code/.worktrees/`，名称应包含
   仓库、任务和 agent 标识。分支遵守本仓现有命名限制，例如 `fix/<task-agent>`。
   不复用其他任务或 agent 的分支、worktree，不在主检出目录或 `main` 上编辑、提交。
2. 只在任务 worktree 中修改授权范围内的文件，保留既有指令和他人的修改。提交前检查
   diff 与暂存区，运行与变更范围匹配的本仓验证。文档修改至少检查
   `git diff --check`、新增命令和链接的有效性及流程完整性，并运行适用的文档检查。
   推送时正常执行现有 hooks，不使用 `--no-verify` 或其他方式绕过门禁。
3. 提交并推送任务分支，通过 PR 合并到 `main`。PR 记录变更范围、实际运行的检查、
   结果和未验证项。只有本地适用门禁和远端 required checks 通过、无合并冲突、
   满足仓库评审要求且获得合并授权后，才可合并。检查失败或无法执行时保留任务状态，
   明确报告阻塞，不直接提交或推送 `main`，不绕过保护规则。
4. 清理前确认 PR 已合并到 `main`，重新获取 `origin/main`，核对合并 SHA 与
   任务分支提交。确认任务分支无尚未进入 main 的独有改动，worktree 无未提交、
   未跟踪或需要保留的忽略文件。squash 或 rebase 合并须核对补丁等价性，不能仅凭
   分支名称判断已合并。存在独有改动或不能证明安全时停止清理并报告。
5. 只清理本任务创建且已确认合并的远端分支、本地分支和 worktree。从 worktree 外
   先运行 `git worktree remove <task-worktree>`，再运行
   `git branch -d <task-branch>`，最后在远端任务分支仍存在且提交未被他人更新时运行
   `git push origin --delete <task-branch>`。不得先删除仍被 worktree 检出的分支。
   安全删除被拒绝时保留现场并报告，不使用 force、`git branch -D`、
   `git reset --hard` 或批量清理，也不删除他人的分支或 worktree。
6. 汇报修改文件、PR 链接、main 合并 SHA、实际检查结果、清理结果和剩余阻塞。
   旧检出未同步时明确说明，不把远端合并等同于本地主检出更新或生产发布。

多个 worktree 共享 Git 配置和 hooks。任务中不得安装、重装或改写共享 hooks、
修改 `core.hooksPath` 或停用校验。生产目录、scheduler、部署配置和生产发布均需
独立授权，本协作流程不授权修改生产环境。
