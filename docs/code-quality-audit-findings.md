# 代码质量审计发现与优化方案

本文档汇总 2026-07-31 对 `market-intel` 主项目及三个子模块（a-share-factor-core、ai-stock-picker、hot-sector-screener）的代码质量盘点结果。文档只列方案，不改动代码。

## 当前状态说明

本文中的整体评价和问题清单主要反映 2026-07-31 的历史状态，不能直接当作当前门禁结果。当前仓库已启用 `pr-light.yml` 和 `public-quality.yml`，两者都会运行部分 pytest，`pytest.yml.disabled`、`cross-market.yml.disabled` 和 `tushare-daily.yml.disabled` 仍处于停用状态。`.gitignore` 已包含 `.coverage`、`.coverage.*` 和 `*.cover`。

截至 2026-09-08，`scripts/dev/maintainability_metrics.py --json --ratchet` 报告 106 个超过 100 列的长行、9 个超过 100 行的函数、2 个超过 800 行的文件和 0 个行内 `C901` 忽略项。当前 ratchet 已通过，后续治理应以这组指标和实际 CI 配置为准。

本文是 [roadmap.md](roadmap.md) 的详细方案与证据附录：roadmap 记录待办项与完成状态，本文给出对应问题的具体方案与排查细节，两者配套阅读。

## 一、整体评价

主项目代码质量明显高于一般脚本型仓库：ruff 全量检查零违规，模块边界清晰，文档化程度高。需要更正一处先前结论：`ty check` 当前仍有 15 个未解决诊断（unresolved-attribute / invalid-argument-type，分布在 `cli.py`、`news_heat.py`、`ai_selection_receipt.py`、`daily_watch20_delivery_receipt.py`、`tushare_jobs/cli.py`），类型门禁尚未真正达标。「返回类型覆盖率 99.7%」的乐观判断已不成立，应以 `ty check` 实际输出为准。主要问题集中在远程测试门禁缺失（pytest.yml 已停用为 .disabled）、`ty` 存量诊断、覆盖率阈值偏低（fail_under=1），以及少量过渡期兼容层长期沉淀。

## 二、测试与门禁（高优先级）

### 2.1 完整自动化测试尚未纳入远程门禁

以下原始问题描述来自 2026-07-31，保留用于说明当时的审计依据。当前启用的 `pr-light.yml` 和 `public-quality.yml` 已运行部分离线 pytest，但完整测试工作流仍处于停用状态。

两个 GitHub Actions 工作流（cross-market.yml、tushare-daily.yml）只做数据快照提交，不跑 pytest。本地 `.githooks/pre-push` 当前是空操作（exit 0）。

方案：
- 在 cross-market.yml、tushare-daily.yml 增加 `uv run pytest` 步骤，或把 pre-push 钩子接回 `project_tools/pre_push_guard.py`（该脚本已有 `tests/test_pre_push_guard.py` 覆盖）。
- 给三个子模块各自补 CI 配置，或至少在 root 提供一个统一入口编排四仓测试。

### 2.2 覆盖率配置盲区
`pyproject.toml` 的 `coverage.source` 只列 `daily_messenger` 一个包，a_share_daily、a_share_analysis、tushare_jobs、ops_common 四个包（占 src 主体）脱离 `fail_under=70` 门禁。

方案：
- 把 `coverage.source` 扩到全部五个包，或为其余四包补 pytest 用例，让核心 A 股逻辑改动有回归约束。

### 2.3 跨仓模型契约检查被静默跳过
`tests/test_ai_stock_picker_shadow.py:64` 在子模块未初始化时 `pytest.skip`，跨仓生产模型一致性检查因此可能不执行。

方案：
- 改为 `pytest.fail` 或在 CI 中强制保证子模块已初始化时运行该检查。

### 2.4 活跃但无测试的模块
`src/a_share_analysis/value_regime_weekly.py` 被 `scripts/weekly_recap.sh` 调用，却没有单元测试。

方案：
- 补一个数值与分区逻辑的单元测试。

### 2.5 四个运维脚本缺 smoke 测试
`scripts/check_index_daily_freshness.py`、`scripts/check_mdp_reference_consistency.py`、`scripts/evening_review_pipeline.py`、`scripts/refresh_a_share_index_daily.py` 没有对应的 `*_script.py` smoke 测试，与现有的 `refresh_daily_watch20.sh` 测试不对称。

方案：
- 为这四个脚本补 `bash -n` 加关键逻辑断言的 smoke 测试，与现有风格对齐。

### 2.6 覆盖率产物误提交风险

该项已核实完成。以下内容保留为历史审计记录。
仓库根 `.coverage`（约 376KB）未被 `.gitignore` 忽略，易误提交。

方案：
- 在 `.gitignore` 增加 `.coverage` 与 `*.coverage`。

## 三、兼容与过渡层（中优先级）

### 3.1 report_delivery 重导出壳
`src/a_share_daily/delivery/report_delivery.py:141-198` 把 senders、state、targets、io_util 四个子模块约 50 个私有符号整包重导出，目的是让旧 `monkeypatch.setattr(report_delivery, ...)` 仍可用。这导致单文件膨胀到 869 行，且出现双命名空间（同一符号可从子模块或 report_delivery 两处 import）。

方案：
- 在测试里把 monkeypatch 目标改为真实子模块，删除 141-198 重导出块。

### 3.2 AI 新闻 gemini 兼容壳
`src/daily_messenger/etl/fetchers/ai_news.py:293-299` 的 `_fetch_gemini_market_news` 是 backward compatible wrapper，仅做同名转发。

方案：
- gemini 调用方迁移完成后删除该壳。

### 3.3 daily_watch20_validation 重导出清理
`src/a_share_daily/daily_watch20_validation/__init__.py` 是空文件，`daily_watch20.py` 曾把该子包的 13 个 `_validate_*` / `_normalize_*` 私有符号 re-export 到顶层 `__all__`，声称保留向后兼容，但全仓测试并无通过 `daily_watch20.X` 访问这些私有符号的用例，属于无引用的兼容负载。

进展（2026-08-01）：已从 `daily_watch20.py` 的 `__all__` 移除这 13 个私有符号的 re-export，子包内部符号改由测试直接 import。空 `__init__.py` 保持不变（子包本身仍被生产代码正常使用）。

### 3.4 targets 内 legacy 分支
`src/a_share_daily/delivery/targets.py:107` 的 `_legacy_chat_id()` 命名带 legacy，仅作内部 fallback。

方案：
- 确认无真实数据源走 legacy 分支后，随新 target 配置全面启用而移除。

## 四、复杂度（中优先级）

### 4.1 高圈复杂度函数
23 个函数 mccabe 复杂度超过 15，最严重：
- `src/a_share_daily/freshness.py:render_freshness_section`（C=28）
- `src/a_share_daily/delivery/report_delivery.py:_deliver_markdown_files_and_images`（C=23）
- `src/daily_messenger/etl/fetchers/btc_flow.py:_fetch_sosovalue_latest_flow`（C=22）
- `src/a_share_daily/delivery/report_delivery.py:_deliver_morning_routes`（C=22）

方案：
- 按现有拆分惯例（git 历史已有多次 C901 拆分）继续拆这些多分支渲染与多源抓取函数。

### 4.2 过渡期验证脚本
`scripts/check_mdp_reference_consistency.py:18-55` 注释写明是 legacy TuShare 路径退役前的验证脚本。

方案：
- MDP 切换完成后删除。→ 已完成（PR #61）：脚本已删除，依赖的 `_compare` 过渡期一致性测试一并移除。

### 4.3 巨型文件兼任双职责
`src/a_share_analysis/factor_tools/minute_factor_smoke.py`（1118 行，全仓最大）既是调试冒烟又是生产批下载器。

方案：
- 拆成 `smoke`（调试/一次性）与 `batch_download`（生产）两个清晰入口。

## 五、Lint 配置（低优先级）

### 5.1 脚本区豁免过宽
`pyproject.toml` 对 `scripts/**` 与 `project_tools/**` 整组禁用 PLR/TRY/EM/S/DTZ/N/C90/RET/SIM/B，运维脚本完全脱离复杂度与风格门禁。

方案：
- 至少对 `scripts/**` 恢复 C90（复杂度）规则，防止脚本无声膨胀。

### 5.2 裸 except 豁免集中
全仓 73 处 `# noqa` 中 57 处是 `BLE001`（裸 except Exception），集中在抓取层。抓取外部源确有容错需求，但数量偏多。

方案：
- 逐步改为捕获具体异常并加日志，降低掩盖真实错误的风险。

### 5.3 飞书发送逻辑重复评估：保留独立实现
初看 `senders.py`、`daily_watch20_lark_delivery.py`、`style_replica_bridge/__init__.py` 三处都调用 `lark-cli`，像是应抽公共 `lark_client` 的重复代码。实测后判定为**有意为之的 specialization，不应强制合并**：

- `senders.py` 内实际有四种不同子进程调用：hermes 发送（120s）、lark 发送（60s，带 cwd）、lark whoami（30s）、lark config bind（60s，带 env），各自超时与错误处理合理。
- `daily_watch20_lark_delivery.py` 支持 dry_run、写投递回执，幂等键带 `hotsector-client-` 前缀（测试断言该前缀）。
- `style_replica_bridge` 仅走 DM、含 fail-closed 准入守卫、无幂等键、超时 30s。

三者幂等策略、回执、准入守卫、超时、target 类型均不同，强行抽公共入口会制造 overloaded 函数、威胁既有测试断言与守卫语义，并让下游包新增对 `ops_common` 的依赖、加剧跨包耦合（与第七节解耦方向相悖）。真正共用的仅是 `subprocess.run(capture_output, text, timeout, check=False)` 这一行样板，收益极低。

S603（subprocess）规则按文件保留豁免。各处命令都在本地构造，没有外部输入，继续放在具体调用点更容易理解。统一封装还需要额外处理 whoami 和 bind 的环境变量与工作目录差异，收益有限。

### 5.4 宽泛 `except Exception` 评估：多为降级容错设计，不盲收窄
全仓 `review.py`（约 11 处）、`pipeline.py`（约 8 处）的 `except Exception` 并非掩盖错误的坏味道，而是系统的降级策略基石：
- `review.py` 的 `except Exception` 包裹 `D.read_xxx(trade_date)` 等数据读取。捕获异常后，该板块留空并显示本交易日暂缺，使报告在部分数据缺失时仍能生成完整页面。
- `pipeline.py` 的 `try_chart` 包裹任意图表生成 `fn`，单图失败不影响其他图。

若强行收窄为具体异常类型（如 `FileNotFoundError / ValueError / KeyError`），反而会因列举不全让某次真实异常击穿降级、导致整份报告失败，降低健壮性。这些保留 `except Exception` 是有意设计。

唯一安全收窄点：`ai_selection_receipt.py` 的 subprocess 调用（`except Exception` 仅用于返回投递错误信息），已收窄为 `except (subprocess.SubprocessError, OSError)`，更精确且不丢行为。

## 六、子模块概览

三个子模块均自带 ruff 配置、规模适中，与主项目同样采用 owner-submodule 加 CLI/JSON 交接模式，无跨仓循环依赖。最大文件在 600 到 800 行区间，属同类项目正常量级。各自复杂度治理由其独立 pyproject 负责，本次未深入。

## 七、团队可维护性建议

- 逻辑未堆在少数文件，145 个模块分布在前述五个职责明确的包中，并非一人一文件垄断。
- 文档边界清晰（architecture.md、boundary-contract.md、contracts.md 等），可维护性基础好。
- 最大隐患是测试门禁与覆盖率盲区（见第二节），建议优先补齐，使核心 A 股逻辑改动有回归保护。
- AGENTS.md 已写明当前为单人维护，分支保护按需开启。若未来恢复多人协作，应同步恢复 CODEOWNERS 与 PR 审查节奏。
