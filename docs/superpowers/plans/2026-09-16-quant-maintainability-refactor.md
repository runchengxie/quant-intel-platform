# Quant 系列维护性重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持生产路径、artifact 契约和公开 CLI 兼容的前提下，降低 quant 系列的模块复杂度、静态检查债务和跨仓依赖风险。

**Architecture:** 每个仓库单独建立任务 worktree 和 PR。先拆分 `quant-intel-platform` 的恢复状态机和投递编排，再处理 `quant-research` 的生产 C901，之后按模块治理 `quant-market-data-platform` 的 lint 债务和 `quant-platform` 的类型债务。跨仓库只通过公开 CLI、版本化 artifact 和 receipt 交互，不复制 owner 实现。

**Tech Stack:** Python 3.11+、Ruff、ty、pytest、uv、MkDocs、TypeScript/Vite、GitHub Pull Requests。

**Spec:** `docs/AGENTS.md`、各仓库 `AGENTS.md`、现有 `scripts/dev/maintainability_metrics.py`、`scripts/dev/quality_debt.py` 和 artifact contract 文档。

## Global Constraints

- 开发代码只在 `/home/richard/code/.worktrees/` 下的独立 worktree 修改。
- `main` 只通过 PR 合并，不直推、不强推、不使用 `reset --hard` 或跳过 hooks。
- 运行数据、研究结果、凭证和虚拟环境留在仓库外。
- 保持现有 CLI、环境变量、artifact schema、manifest 和 receipt 字段兼容。
- provider 仓库先于 consumer 仓库合并，生产切换单独执行并保留回滚版本。
- 每个任务完成后运行与改动范围匹配的测试，并记录真实结果。

---

### Task 1: 拆分 `quant-intel-platform` 恢复状态机

**Files:**
- Create: `src/ops_common/recovery_state.py`
- Create: `src/ops_common/recovery_probes.py`
- Create: `src/ops_common/recovery_actions.py`
- Modify: `src/ops_common/scheduled_recovery.py`
- Test: `tests/test_scheduled_recovery.py`

**Interfaces:**
- `recovery_state.py` 提供状态 JSON 读取、原子写入、失败指纹和禁用阶段解析函数。
- `recovery_probes.py` 提供 systemd、artifact freshness、current contract 和 timer/service 探测函数。
- `recovery_actions.py` 提供阶段恢复命令、重试预算和失败通知函数。
- `scheduled_recovery.py` 继续导出 `reconcile()`、`run()` 及现有模块级兼容符号。

- [ ] **Step 1: 为状态、探测和动作边界补测试**

  在 `tests/test_scheduled_recovery.py` 中增加状态读写、探测失败、重试预算耗尽和通知失败不覆盖主失败状态的测试。测试只使用 `tmp_path` 和 fake subprocess，不启动真实 systemd。

- [ ] **Step 2: 运行恢复模块测试确认边界测试失败**

  ```bash
  uv run --locked --group dev python -m pytest tests/test_scheduled_recovery.py -q
  ```

- [ ] **Step 3: 移动纯函数和数据结构**

  将状态 JSON、失败指纹、禁用阶段和 freshness 读取逻辑移入 `recovery_state.py`，将 systemd 属性和 timer/service 探测移入 `recovery_probes.py`，保持原函数签名并在旧模块中重新导入。

- [ ] **Step 4: 移动恢复动作和通知逻辑**

  将恢复命令构造、预算判断、阶段执行和失败通知移入 `recovery_actions.py`。`scheduled_recovery.py` 只保留阶段依赖图、编排顺序和 CLI 入口。

- [ ] **Step 5: 运行完整本地门禁**

  ```bash
  uv run --locked --group dev python -m pytest tests/test_scheduled_recovery.py tests/test_ops_common.py -q
  uv run --locked --group dev ruff check src tests
  uv run --locked --group dev ruff format --check src tests
  uv run --locked --group dev ty check
  uv run --locked --group dev python project_tools/check_all.py --scope all
  ```

- [ ] **Step 6: 提交并创建 PR**

  ```bash
  git add src/ops_common tests/test_scheduled_recovery.py
  git commit -m "refactor: split scheduled recovery state machine"
  git push -u origin fix/scheduled-recovery-modules
  gh pr create --base main --head fix/scheduled-recovery-modules
  ```

### Task 2: 拆分投递与 weekly basket CLI 编排

**Files:**
- Create: `src/a_share_daily/delivery/routes.py`
- Create: `src/a_share_daily/weekly_basket_command.py`
- Modify: `src/a_share_daily/delivery/report_delivery.py`
- Modify: `src/a_share_daily/cli.py`
- Test: `tests/test_a_share_report_delivery.py`
- Test: `tests/test_weekly_client_basket.py`

**Interfaces:**
- `routes.py` 提供 Lark、Hermes、webhook 路由执行函数，返回现有 route 状态结构。
- `weekly_basket_command.py` 提供 `run_weekly_basket(args) -> int`，保留 CLI 参数和输出 JSON 字段。
- 原模块保留兼容导入，外部调用无需改路径。

- [ ] **Step 1: 锁定现有投递和 CLI 行为**

  ```bash
  uv run --locked --group dev python -m pytest tests/test_a_share_report_delivery.py tests/test_weekly_client_basket.py -q
  ```

- [ ] **Step 2: 把路由发送和 receipt 写入移入 `routes.py`**

  保持 `_deliver_via_lark`、`_deliver_via_hermes`、`_deliver_via_webhook` 的参数和返回值，`report_delivery.py` 只负责准备上下文和调用路由。

- [ ] **Step 3: 把 weekly basket 的输入、锁定、渲染和发送编排移入 `weekly_basket_command.py`**

  `cli.py::_cmd_weekly_basket` 只负责参数分发和异常转换，`--dry-run`、`--send` 互斥规则及现有错误码保持不变。

- [ ] **Step 4: 运行门禁并检查维护性指标**

  ```bash
  uv run --locked --group dev ruff check src tests
  uv run --locked --group dev python project_tools/check_all.py --scope all
  uv run --locked --group dev python scripts/dev/maintainability_metrics.py --ratchet
  ```

### Task 3: 清理 `quant-research` 剩余 C901

**Files:**
- Modify: `src/quant_execution_engine/cli/__init__.py`
- Modify: `src/ticknet/eventstream/train.py`
- Modify: `src/ticknet/nextday/dataset.py`
- Modify: `src/ticknet/nextday/formal_targets.py`
- Modify: `src/ticknet/nextday/minute_materialization.py`
- Modify: `src/ticknet/nextday/train.py`
- Test: 对应 `tests/microstructure/` 和 `tests/strategy_research/` 测试

- [ ] **Step 1: 为每个 C901 函数记录当前输入输出和异常行为**

  ```bash
  uv run --locked --extra dev ruff check src --select C901 --output-format concise
  uv run --locked --extra dev python -m pytest tests/microstructure tests/strategy_research -q
  ```

- [ ] **Step 2: 先拆 CLI 分发和 dataset 初始化**

  把参数解析、配置校验、资源加载和训练调用拆成独立函数，保留公开命令和异常消息。

- [ ] **Step 3: 再拆 nextday 标签、分钟物化和训练循环**

  将日期窗口、候选筛选、状态报告、批处理和模型训练拆开，每个函数只保留单一阶段。

- [ ] **Step 4: 更新 C901 基线并运行完整相关测试**

  ```bash
  uv run --locked --extra dev python scripts/dev/ruff_layers.py --layer production --check-baseline
  uv run --locked --extra dev python -m pytest tests/microstructure tests/strategy_research -q
  ```

### Task 4: 分阶段治理 `quant-market-data-platform` lint 债务

**Files:**
- Modify: `scripts/dev/quality_debt.py`
- Modify: `scripts/dev/quality_baseline.json`
- Modify: 每次 PR 明确列出的 provider 模块
- Test: 对应 provider 测试和 `tests/test_quality_debt.py`

- [ ] **Step 1: 将 F401 分为公共导出、兼容导出和无用导入**

  使用 import graph 和 `__all__` 逐文件确认调用方，每个 PR 最多处理一个 provider 子域。

- [ ] **Step 2: 将 RUF100 分为默认 Ruff 规则和复杂度扫描规则**

  让质量报告分别统计两类 `noqa`，保留 C90/PLR 复杂度检查所需的标记。

- [ ] **Step 3: 每个子域删除已证明无用的导入并补回归测试**

  ```bash
  uv run --locked --extra dev python -m pytest tests -q
  uv run --locked --extra dev python -m ruff check .
  uv run --locked --extra dev python scripts/dev/quality_debt.py --check-baseline
  ```

### Task 5: 处理 `quant-platform` 类型债务

**Files:**
- Modify: 每个 PR 明确列出的公共 API 或执行引擎模块
- Test: 对应单元测试和类型边界测试

- [ ] **Step 1: 按 package 统计 ty 诊断和 unresolved import**

  先处理 `quant_execution_engine`、artifact contract 和路径解析模块，暂不修改历史实验脚本。

- [ ] **Step 2: 为 DataFrame、配置对象和 receipt 补充窄类型**

  用 TypedDict、Protocol 和显式转换替代大范围 `Any`，不改变运行时数据结构。

- [ ] **Step 3: 运行分层类型检查和完整测试**

  ```bash
  uv run --locked --extra dev ty check
  uv run --locked --extra dev ruff check .
  uv run --locked --extra dev pytest -q
  ```

### Task 6: 清理 `quant-market-research` Web 提示并检查构建体积

**Files:**
- Modify: `web/src/**/*.ts`、`web/src/**/*.tsx`
- Test: `web` 下现有测试和静态校验

- [ ] **Step 1: 清理未使用导入和类型提示**

  ```bash
  cd web
  npm ci
  npm test
  npm run build
  npm run verify:static
  ```

- [ ] **Step 2: 对大 chunk 做页面级动态导入**

  保持公开路由、静态数据路径和 GitHub Pages 输出不变。

### Task 7: 建立跨仓库依赖和 artifact 一致性检查

**Files:**
- Create: `quant-intel-deploy/scripts/check_release_graph.py`
- Create: 各 owner 仓库对应 contract 测试
- Modify: `quant-intel-deploy/docs/boundary-contract.md`

- [ ] **Step 1: 检查 provider、consumer 和 deploy pin 的版本关系**

  输入为显式仓库路径和 production `current` 路径，输出 JSON，包含 commit、manifest、schema 和 receipt 哈希。

- [ ] **Step 2: 在无真实数据和无发送模式下验证版本链**

  ```bash
  python scripts/check_release_graph.py --production-root /home/richard/code/production --json
  bash -n scripts/*.sh
  ```

- [ ] **Step 3: 将检查接入本地发布门禁**

  失败时阻止生产切换，成功时记录回滚版本和外部数据根目录。
