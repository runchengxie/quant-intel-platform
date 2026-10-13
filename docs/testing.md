[English page](testing.en.md)

# 测试与质量保障

## 本仓质量入口

```bash
uv sync --locked --group dev
uv run python project_tools/check_all.py --scope all
uv run pytest -k cli_pipeline --maxfail=1
uv run pytest -k contract
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest --cov --cov-report=term-missing
uv run python project_tools/package_coverage.py
uv run python project_tools/update_cli_help.py --check
```

`check_all.py` 只检查 `market-intel` 根仓及其脚本。历史三个 submodule 已退休，各 owner 仓运行各自门禁。本仓不得再次通过相邻目录扫描替 owner 跑测试。

`check_all.py` 统计 `src/` 下全部 Python 生产模块，包括未被测试导入的文件，并逐包检查最低行覆盖率。漏测文件或新增包缺少门槛时，门禁会失败。以下基线来自 2026-10-12 的锁定依赖全量合成测试，已有五个包的门槛保持不变，新增包的门槛留出少量回归空间。市场评论和发布包的覆盖率仍偏低，当前门槛只用于防止继续退化，不能视为充分验证。

| 生产包 | 本次基线 | 最低门槛 |
| --- | ---: | ---: |
| `a_share_analysis` | 81.14% | 70% |
| `a_share_daily` | 76.82% | 65% |
| `daily_messenger` | 79.13% | 65% |
| `market_intel_commentary` | 15.11% | 10% |
| `market_intel_config` | 100.00% | 90% |
| `market_intel_publication` | 38.33% | 35% |
| `ops_common` | 64.27% | 50% |
| `research_contracts` | 79.74% | 70% |
| `style_replica_bridge` | 31.34% | 25% |
| `tushare_jobs` | 44.51% | 35% |

覆盖率数据默认保存到 `.coverage`，可通过 `COVERAGE_FILE` 指定仓库外路径，采集器和逐包门禁使用同一个文件。合成测试的临时产物应写入仓库外目录。发布边界测试拒绝写入 owner checkout 或其他源码仓库。默认临时目录受其他 `.git` 标记影响时，通过 `TMPDIR` 或 pytest 的 `--basetemp` 选择新的外部测试目录，不移除标记或关闭安全 guard。`--basetemp` 会清理指定目录，因此不能指向已有数据、源码或生产目录。

PR 和 `main` 推送会运行 `check_all.py --scope all --strict-tools`，并构建 Python 包、检查公开边界。完整质量结果由 GitHub Actions 提供；本地可运行同一门禁提前验证。

删除已合并分支时，先用独立清理命令确认 PR 状态。它默认只检查，提供 `--yes` 才执行
删除：

```bash
uv run python project_tools/cleanup_merged_branches.py \
  --repo runchengxie/quant-intel-platform \
  --branch fix/example \
  --dry-run
uv run python project_tools/cleanup_merged_branches.py \
  --repo runchengxie/quant-intel-platform \
  --branch fix/example \
  --yes
```

GitHub Actions 在 PR 和 `main` 推送时运行完整代码质量门禁，不访问真实市场数据、不调用飞书或券商。生产数据访问和部署验证仍须按对应手册单独执行。生产数据调度由 Deploy 管理，不属于本仓质量门禁。

## 负责方边界测试

本仓测试应重点覆盖：

- ETL、主题评分、市场资讯与降级行为
- 产物日期、结构、哈希的安全失败校验
- DailyWatch20、D11-H5、style-factor 等 owner 产物的消费
- 报告渲染、图表、看板与受众隔离
- 飞书幂等、投递回执和失败恢复
- 调度与恢复逻辑不会安装或修复研究侧定时器
- Deploy 的 `refresh_daily_watch20.sh` 只通过已安装的 `daily-watch20-owner` CLI 恢复正式 artifact，其脚本测试由 Deploy 维护。

分钟因子研究、Hermite、滚动训练、OOS、消融、AI 排名和影子运行等算法测试归 `quant-research` 负责，market-intel 不保留重复测试。

## 部署与调度验证

Hermes、systemd 和 Windows Task Scheduler 的脚本、模板及主机 smoke 流程由私有 `quant-intel-deploy` 维护。`ensure_hermes_gateway.sh`、`setup_cron.sh` 和 `scripts/windows/test_scheduled_tasks.ps1` 不在本仓，不能作为本仓测试命令执行。

本仓只验证公开 CLI、artifact 契约和离线样例。主机状态检查、一次性调度任务和真实投递验证按 Deploy 的 runbook 与独立授权执行，不改变主机时钟，不停止生产服务作为测试手段。

## 核心测试分类

| 范围 | 关注点 |
| --- | --- |
| ETL / feeds | RSS、API 解析、重试、模拟与降级 |
| scoring / digest | 主题得分、建议、渲染和快照 |
| contracts | JSON/artifact/receipt 字段和日期约束 |
| A 股报告 | 晨晚报结构、图表路径、旧图防护、缺数据边界 |
| DailyWatch20 consumer | 正式 artifact 校验、raw completeness、投递回执 |
| delivery | lark-cli/webhook、受众隔离、幂等 |
| recovery | freshness DAG、重试预算、窗口、owner 边界 |
| Dashboard | payload、状态面板、HTML 输出 |
| TuShare compat | 报告侧导出、存储与窗口处理 |

测试数量以当前 `uv run pytest` 输出为准，不在文档写死。

## 质量要求

- Ruff lint 与 format 通过
- `ty check` 覆盖根项目 `src/`
- `pytest` 与 contract tests 通过
- CLI help 与 `docs/cli-reference.md` 同步
- shell、PowerShell、JS 脚本在可用工具下通过静态检查
- 跨仓功能如果依赖 owner 改动，provider PR 和对应 owner commit 必须先有可审计记录。

通过 GitHub connector 创建的 PR 无法替代本机 `uv`/systemd/live-provider 验证。因此这类大规模边界迁移在真实本地门禁和部署 smoke 完成前应保持 Draft。
