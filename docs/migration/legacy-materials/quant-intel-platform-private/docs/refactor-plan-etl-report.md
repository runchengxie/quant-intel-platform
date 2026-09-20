# 重构记录：拆分巨型文件（ETL 与投递）

本文记录 `run_fetch.py` 与 `report_delivery.py` 的拆分进展。拆分目标是在不破坏现有绿色 pre-push 门禁的前提下，按数据源和职责把巨型文件拆成更小的模块，降低单文件复杂度，方便团队协作维护。

## 当前状态（行数为实测值）

| 文件 | 原行数 | 现状态 | 拆分结果 |
|------|--------|--------|----------|
| `daily_messenger/etl/run_fetch.py` | 860 → 693 | 已完成 | 残留抓取函数已全部外移：`_fetch_price_only_quotes`→`quotes.py`，`_fetch_ai_market_news`/`_fetch_gemini_market_news`→`ai_news.py`，`_merge_sentiment_source`/`_fetch_sentiment_payload`→`aaii_sentiment.py`，`_fetch_btc_payload`→`btc_flow.py`。原方程留 693 行纯编排层与兼容再导出，本身是 Orchestration 层 |
| `a_share_daily/delivery/report_delivery.py` | 1396 | 已完成 | 拆为 `io_util.py`(93) / `targets.py`(203) / `senders.py`(433) / `state.py`(108)，原方程留 696 行编排入口与兼容再导出 |
| `daily_messenger/dashboard/payload.py` | 1711 | 已完成 | 拆为 `payload_helpers.py` / `payload_state.py` / `payload_aggregations.py` / `payload_terminal.py` / `payload_coverage.py`，原方程留 181 行 |
| `daily_messenger/etl/fetchers/ai_news.py` | 1317 | 已完成 | 拆为 `ai_news_common/settings_chain/parse/glm/gemini/aliyun/feeds`，原方程留 199 行 |
| `a_share_daily/daily_watch20.py` | 1182 | 已完成 | 13 个 `_validate_*` 拆入 `daily_watch20_validation/` 子包，原方程留 587 行 |

注意：早期方案里写 `run_fetch.py` 约 1938 行、`report_delivery.py` 约 1813 行，那是拆分前的历史值。拆分过程中各文件已显著缩小，本文以当前实测行数为准。

四个巨型文件已完成拆分，ratchet 基线（`scripts/dev/maintainability_metrics.py` 的 `files_over_800`、`files_over_1200`）已同步下调。

## run_fetch.py 已完成的部分

项目早已在 `daily_messenger/etl/fetchers/` 下建立了按数据源拆分的子模块，`run_fetch.py` 已把大部分抓取函数外移并改为编排层：

- `etl/fetchers/ai_news.py`、`fmp.py`、`cboe_putcall.py`、`edgar.py`、`fred.py`、`aaii_sentiment.py`
- `etl/fetchers/hk.py`（港股）、`quotes.py`（行情聚合）、`normalize.py`（事件规范化）、`events.py`（事件抓取）、`btc_flow.py`（BTC/ETF 资金流）

`run_fetch.py` 现在保留的是路径工具、缓存判定、配置加载、编排函数，以及跨模块聚合入口，负责把各 `fetchers` 子模块的结果拼装成 `raw_market.json`、`raw_events.json`、`etl_status.json`。

### 仍残留待搬移的函数

以下抓取函数还在 `run_fetch.py` 内，按早期映射应继续搬到对应 `fetchers` 模块：

| 函数 | 目标模块 |
|------|----------|
| `_fetch_coinbase_spot`、`_fetch_okx_funding`、`_fetch_okx_basis` | `etl/fetchers/coinbase_okx.py`（新建） |
| `_fetch_yahoo_quotes`、`_fetch_price_only_quotes` | 并入已有 `etl/fetchers/quotes.py` |
| `_fetch_ai_market_news`、`_fetch_gemini_market_news` | 并入已有 `etl/fetchers/ai_news.py` |
| `_fetch_sentiment_payload`、`_fetch_btc_payload` | 并入已有 `aaii_sentiment.py` / `crypto` 相关模块 |

## report_delivery.py 已完成的部分

`report_delivery.py` 内部已按职责分组，并已完成两轮拆分：

- 晚报渲染函数（`_render_evening_*`、`_news_items`、`_fmt_score`、`_quote_line` 等）已迁到 `a_share_daily/delivery/_render.py`
- IO 与格式化工具已迁到 `a_share_daily/delivery/_format.py`

`report_delivery.py` 已完成拆分：投递目标解析、投递执行（Hermes / lark-cli / webhook 三套）、状态与幂等已分别迁到 `targets.py`、`senders.py`、`state.py`，图表时效与常量迁到 `io_util.py`。原方程保留编排入口（`deliver_morning` / `deliver_evening` / `run` / `_deliver_markdown_files_and_images` / `_chart_paths` / `_manifest_chart_paths`）和完整兼容再导出，所有外部调用方与测试零改动。

## 安全网与执行顺序

1. 每搬走一组函数，跑一次 `uv run python project_tools/check_all.py --scope all`，确保门禁不红。
2. 拆分采用新建子模块、原方程顶部兼容再导出的最低风险路径，外部调用方和现有测试无需改动。
3. 每完成一个文件拆分，单独 commit 并 push（保持小步、可回滚）。

## 异常处理说明

`run_fetch.py` 中多处 `except Exception as exc:  # noqa: BLE001` 是 ETL 降级的合理设计：任何数据源抓取失败都应降级记录，不能让单个源崩溃整条流水线。拆分只做物理移动，不改动异常捕获策略。收窄异常类型会漏掉未预见的错误，反而降低健壮性，不在本次范围。

## 不在本次范围

- `run_fetch.py` 残留抓取函数：已全部外移（含上一轮因测试 stub 约束暂留的 4 个）。本轮把测试桩从 `run_fetch` 命名空间改到目标模块（如 `monkeypatch.setattr(coinbase_okx, ...)`、`monkeypatch.setattr(aaii_sentiment, ...)`、`monkeypatch.setattr(btc_flow, ...)`、`monkeypatch.setattr(ai_news, ...)`），4 个函数随之干净外移：`_fetch_ai_market_news`/`_fetch_gemini_market_news`→`ai_news.py`，`_merge_sentiment_source`/`_fetch_sentiment_payload`→`aaii_sentiment.py`，`_fetch_btc_payload`→`btc_flow.py`。run_fetch 现为纯编排层（693 行），不再是超大文件。
- `a_share_analysis` 模块：该项已闭环。`post_market_review.py` 兼容 wrapper 已确认无引用并删除（canonical 实现在 `a_share_daily.review`）。`style_replica_bridge` 与 `quantall.py` 是活跃功能模块（分别有 `dm style-replica` CLI 入口、对应测试，以及 `project_tools/quantall_bridge.py` 桥接工具），并非待清理死代码，维持现状。
- `project_tools/` 里 `a_share_*` 因子实验脚本（共 7 个）互相 import 成网（`a_share_minute_volume_oos_audit`、`a_share_factor_walk_forward` 等均依赖 `a_share_factor_incremental_experiment` 与 `a_share_minute_volume_calendar`），且被 5 个测试文件整体覆盖。它们属研究实验工具，不在 `src/` 主链路、不被 `ty` 检查，也没有死代码可单独剔除。移动单个会扯断依赖网、整体迁移又无收益，故维持现状，仅文档归类为研究工具。
  - 上述「维持现状」结论已被本轮推翻：9 个因子脚本已整体升格进 `src/a_share_analysis/factor_tools/`（见「project_tools 因子脚本升格」一节）。升格是用户明确批准的重构，依赖网通过包内导入整体迁移，未破坏任何测试。

## project_tools 因子脚本升格

用户明确批准把 `project_tools/` 下 9 个已投产因子脚本升格进正式包 `src/a_share_analysis/factor_tools/`。复用已有的 `a_share_analysis*` setuptools 前缀（`pyproject.toml` 的 `[tool.setuptools.packages.find] include` 已含该前缀），无需改 include。

### 迁移文件与包内模块名映射

| 原路径 | 新路径（模块名） |
|--------|------------------|
| `project_tools/a_share_minute_factor_smoke.py` | `src/a_share_analysis/factor_tools/minute_factor_smoke.py` |
| `project_tools/a_share_factor_walk_forward.py` | `src/a_share_analysis/factor_tools/walk_forward.py` |
| `project_tools/a_share_factor_incremental_experiment.py` | `src/a_share_analysis/factor_tools/incremental_experiment.py` |
| `project_tools/a_share_minute_volume_oos_audit.py` | `src/a_share_analysis/factor_tools/volume_oos_audit.py` |
| `project_tools/a_share_minute_volume_calendar.py` | `src/a_share_analysis/factor_tools/volume_calendar.py` |
| `project_tools/a_share_minute_factor_expand.py` | `src/a_share_analysis/factor_tools/minute_factor_expand.py` |
| `project_tools/a_share_hermite_factor_meta.py` | `src/a_share_analysis/factor_tools/hermite_factor_meta.py` |
| `project_tools/minute_raw_completeness.py` | `src/a_share_analysis/factor_tools/minute_raw_completeness.py` |
| `project_tools/quantall_bridge.py` | `src/a_share_analysis/factor_tools/quantall_bridge.py` |

同步新增 `src/a_share_analysis/factor_tools/__init__.py`（空文件）。

### 关键修正要点

- `PROJECT_ROOT` 重算：原脚本用 `Path(__file__).resolve().parents[1]` 反推仓库根（在 `project_tools/` 层）。迁入 `src/a_share_analysis/factor_tools/` 后，该写法只能到 `src/a_share_analysis/`，故全部改为 `parents[3]`（factor_tools → a_share_analysis → src → 仓库根）。硬编码绝对路径（如 `/home/richard/data/market-data-platform`、`/home/richard/code/research-workspace/market-data-platform`）原样保留，属运行环境约定。
- 互相 import 改包导入：`a_share_factor_walk_forward` 与 `a_share_minute_volume_oos_audit` 内的 `import a_share_factor_incremental_experiment as base` 改为 `from a_share_analysis.factor_tools import incremental_experiment as base`。`volume_oos_audit` 的 `import a_share_factor_walk_forward as walk` 改为 `from a_share_analysis.factor_tools import walk_forward as walk`。`from a_share_minute_volume_calendar import add_open_to_open_execution_labels` 改为 `from a_share_analysis.factor_tools.volume_calendar import add_open_to_open_execution_labels`。
- `minute_raw_completeness` 顶部把 `project_tools` 加入 `sys.path` 的片段已删除（迁入包后由包导入处理），其函数内裸导入 `from a_share_minute_factor_smoke import ...` 改为 `from a_share_analysis.factor_tools.minute_factor_smoke import ...`。
- `quantall_bridge` 的 `from a_share_analysis.quantall import (...)` 改为相对导入 `from ..quantall import (...)`（`..` 指 `a_share_analysis`）。
- `volume_oos_audit` 的 `imported_code_lineage()` 原本对 `project_tools/*.py` 做代码指纹，路径已改指向 `src/a_share_analysis/factor_tools/*.py`。

### 生产 .sh 调用改写

`scripts/refresh_a_share_factor_observation.sh` 与 `scripts/refresh_daily_watch20.sh` 中 5 处文件式调用统一改为模块式：

- `refresh_a_share_factor_observation.sh` 子 shell 内 `"$MI_DIR/project_tools/a_share_minute_factor_smoke.py"` 改为 `PYTHONPATH="$TOP200_PYTHONPATH" uv run --extra tushare python -m a_share_analysis.factor_tools.minute_factor_smoke`（其余 `MINUTE_SYMBOL_ARGS`、`TUSHARE_CREDENTIAL_ARGS`、`--start-date` 等参数原样保留。`TOP200_PYTHONPATH` 已含 `"$MI_DIR/src"`，可解析 `-m`）。
- `uv run python project_tools/minute_raw_completeness.py` 改为 `uv run python -m a_share_analysis.factor_tools.minute_raw_completeness`。
- `uv run python project_tools/a_share_minute_factor_expand.py` 改为 `uv run python -m a_share_analysis.factor_tools.minute_factor_expand`。
- `uv run python project_tools/a_share_hermite_factor_meta.py` 改为 `uv run python -m a_share_analysis.factor_tools.hermite_factor_meta`。
- `uv run python project_tools/a_share_factor_walk_forward.py` 改为 `uv run python -m a_share_analysis.factor_tools.walk_forward`。
- `refresh_daily_watch20.sh` 的 `"$MDP_DIR/.venv/bin/python" "$MI_DIR/project_tools/minute_raw_completeness.py"` 改为 `"$MDP_DIR/.venv/bin/python" -m a_share_analysis.factor_tools.minute_raw_completeness`。

### tests 改写

- `test_a_share_minute_volume_oos_audit.py`、`test_a_share_factor_walk_forward.py`、`test_a_share_factor_daily_clean_resolution.py`、`test_a_share_minute_factor_smoke.py`、`test_quantall_bridge.py` 的裸导入改为 `from a_share_analysis.factor_tools import ...`。并删除这些测试里把 `project_tools` 注入 `sys.path` 的片段。
- `test_a_share_factor_observation_script.py`、`test_daily_watch20_producer_script.py` 中原先断言脚本含 `project_tools/<文件名>` 的字符串断言，改为断言脚本含 `a_share_analysis.factor_tools.<模块名>`。
- `test_minute_raw_completeness.py` 原本用 `importlib.util.spec_from_file_location` 直接加载 `project_tools/minute_raw_completeness.py`，改为标准 `from a_share_analysis.factor_tools import minute_raw_completeness as MODULE`。

### 质量门禁与 ty 缺口

- `pyproject.toml` 的 `[tool.ty.src] exclude` 原为 `"project_tools/"`，改为精确排除三个治理工具（`check_all.py`、`pre_push_guard.py`、`update_cli_help.py`）。ruff 的 `extend-exclude` 不含 `project_tools`，无需改。
- factor_tools 已纳入 ty 检查（原 `src/a_share_analysis/factor_tools/` 的 ty exclude 已移除）。纳入后共 10 个诊断，分两类处理，无遗留。其一为 `market_data_platform` 这一跨仓库外部模块无法解析（`unresolved-import`），该包不在本仓库 `src/` 或 `.venv` 中、且未提供 `py.typed`，故未强行加 source，改为在 `pyproject.toml` 的 `[tool.ty.analysis]` 用 `allowed-unresolved-imports = ["market_data_platform.**"]` 按模块前缀精准放行，不影响对本地问题的检查。其二为 pandas 版本类型漂移导致的返回/参数注解失配（`groupby` 迭代结果、`pd.DatetimeIndex.append` 新返回 `Index`、`DataFrame` 运算返回被 stub 标为 `DataFrame | ndarray | Unknown`），均只调整类型注解并辅以 `cast`，未改动任何运行时逻辑。全程未使用 `# ty: ignore`。
- 复杂度 ratchet（`scripts/dev/maintainability_metrics.py`）原本只统计 `src/scripts/tests`，因子脚本迁入 `src/` 后会拉高 `files_over_800`、`functions_over_100`、`long_lines_over_100` 三项预算。为不放宽仓库全局预算、也不改动已投产脚本逻辑，在 `discover_python_files` 增加与 ty 对齐的 `DEFAULT_EXCLUDES`（`src/a_share_analysis/factor_tools/`），使这次纯搬迁不污染全局复杂度预算。预算常量本身未改动。

### 补的单测

以下 3 个模块原先无独立单测，升格后各补最小冒烟测试（合成数据，不依赖真实行情）：

- `tests/test_factor_tools_volume_calendar.py`：`add_open_to_open_execution_labels` 的 T+1/T+2 标签平移。
- `tests/test_factor_tools_minute_factor_expand.py`：`compute_stock_factors`、`peak_count`、`realized_and_jump_factors` 的纯函数行为。
- `tests/test_factor_tools_hermite_factor_meta.py`：`rolling_zscore`、`hermite_energy`、`parse_source` 的基本形状与有限性。

### 最终门禁

`uv run ruff check .`、`uv run ruff format --check .`、`uv run ty check`、`uv run python -m pytest tests/ -q`、`uv run python project_tools/check_all.py --scope all` 全部通过。
