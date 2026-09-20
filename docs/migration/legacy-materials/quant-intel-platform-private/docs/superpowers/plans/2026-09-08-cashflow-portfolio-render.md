# Cashflow Portfolio Render Refactor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拆分现金流组合 PNG 渲染函数，降低生产函数长度，同时保持现有图表和文件输出契约。

**Architecture:** 保留 `render_cashflow_portfolio_png()` 作为公开分发入口，将研究组合和可执行组合的绘图逻辑分别放入内部 helper。再抽取公共的 PNG 原子写入逻辑，避免两个渲染分支重复管理临时文件和清理流程。

**Tech Stack:** Python、Matplotlib、pytest、Ruff、维护性指标脚本。

**Spec:** `docs/quant-maintenance-closure.md` 中记录的 `quant-intel-platform` 维护性指标治理目标。

## Global Constraints

- 保持 `render_cashflow_portfolio_png(artifact, output_path) -> Path` 的公开签名不变。
- 保持研究图和可执行图的文字、布局、颜色、PNG 格式和输出路径行为不变。
- 不新增 `C901` 忽略项，不放宽 ratchet 预算。
- 现有 `tests/test_cashflow_portfolio_render.py` 必须继续通过。

---

### Task 1: 抽取研究组合 PNG 渲染 helper

**Files:**
- Modify: `src/a_share_daily/cashflow_portfolio_render.py:217-346`
- Test: `tests/test_cashflow_portfolio_render.py`

- [x] **Step 1: 运行现有研究图测试建立基线**

运行：`uv run --locked --group dev pytest tests/test_cashflow_portfolio_render.py::test_portfolio_png_is_written_as_a_real_chart -q`

预期：测试通过，确认当前 PNG 输出契约。

- [x] **Step 2: 将研究图绘制逻辑移入 `_render_research_png()`**

保留公开函数对 `_is_executable(artifact)` 的分发逻辑，将研究分支中的 Matplotlib 初始化、布局、图表绘制和保存前准备移到内部 helper。helper 接收 `artifact`、`targets`、`output_path` 和主题对象所需参数，不改变图中文字和数据。

- [x] **Step 3: 验证研究图测试和维护性指标**

运行：`uv run --locked --group dev pytest tests/test_cashflow_portfolio_render.py::test_portfolio_png_is_written_as_a_real_chart -q`

运行：`uv run --locked --group dev python scripts/dev/maintainability_metrics.py --ratchet`

预期：测试通过，函数数量超过 100 行的指标下降至少 1，ratchet 仍通过。

- [x] **Step 4: 提交**

```bash
git add src/a_share_daily/cashflow_portfolio_render.py tests/test_cashflow_portfolio_render.py
git commit -m "refactor: split research cashflow chart rendering"
```

### Task 2: 抽取可执行组合 PNG 渲染 helper

**Files:**
- Modify: `src/a_share_daily/cashflow_portfolio_render.py:451-571`
- Test: `tests/test_cashflow_portfolio_render.py`

- [x] **Step 1: 运行现有可执行图测试建立基线**

运行：`uv run --locked --group dev pytest tests/test_cashflow_portfolio_render.py::test_executable_png_uses_top_holdings_and_execution_kpis -q`

预期：测试通过，确认可执行图输出契约。

- [x] **Step 2: 抽取公共 PNG 原子保存 helper**

将 `Path(output_path).expanduser().resolve()`、父目录创建、临时文件命名、`fig.savefig()`、替换和 finally 清理提取为内部 helper。研究图和可执行图都使用同一保存流程。

- [x] **Step 3: 保留可执行图绘制边界并减少函数长度**

让 `_render_executable_png()` 只负责读取 artifact、准备布局、调用现有绘图 helper 和提交 Figure。保持表格、行业分布和 KPI 文案不变。

- [x] **Step 4: 验证目标测试和维护性指标**

运行：`uv run --locked --group dev pytest tests/test_cashflow_portfolio_render.py -q`

运行：`uv run --locked --group dev ruff check src/a_share_daily/cashflow_portfolio_render.py`

运行：`uv run --locked --group dev python scripts/dev/maintainability_metrics.py --ratchet`

预期：全部测试通过，两个原始超长函数不再出现在 largest functions，ratchet 预算只收紧或保持。

- [x] **Step 5: 提交**

```bash
git add src/a_share_daily/cashflow_portfolio_render.py
git commit -m "refactor: share cashflow chart output handling"
```

### Task 3: 完成分支验证

**Files:**
- Modify: `docs/quant-maintenance-closure.md`

- [x] **Step 1: 运行完整相关测试**

运行：`uv run --locked --group dev pytest tests/test_cashflow_portfolio_render.py tests/test_a_share_report_delivery.py -q`

- [x] **Step 2: 运行完整静态和维护性检查**

运行：`uv run --locked --group dev ruff check .`

运行：`uv run --locked --group dev python scripts/dev/maintainability_metrics.py --ratchet`

- [x] **Step 3: 更新收口记录并提交**

记录最新长行、超长函数和大文件指标，提交：

```bash
git add docs/quant-maintenance-closure.md
git commit -m "docs: record cashflow renderer refactor metrics"
```
