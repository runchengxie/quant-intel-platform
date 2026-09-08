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
uv run pytest --cov-report=term-missing
uv run python project_tools/update_cli_help.py --check
```

`check_all.py` 只检查 `market-intel` 根仓及其脚本。历史三个 submodule 已退休，research-workspace 和各 owner 仓运行各自门禁。本仓不得再次通过相邻目录扫描替 owner 跑测试。

## 本地 pre-push

```bash
uv run python scripts/dev/install_git_hooks.py
uv run python scripts/dev/install_git_hooks.py --check
```

钩子只安装到 `market-intel` 根仓：

- 推送 `main` 或 tag：运行 `check_all.py --scope all`。
- 推送 `feat/*`、`fix/*`、`hotfix/*`、`chore/*`、`release/*`：运行根仓检查和非 Python 脚本检查。
- 其他远端分支名、删除 `main` 或删除 tag：拒绝。

删除已合并分支时，先用独立清理命令确认 PR 状态。它默认只检查，提供 `--yes` 才执行
删除：

```bash
uv run python project_tools/cleanup_merged_branches.py \
  --repo runchengxie/market-intel \
  --branch fix/example \
  --dry-run
uv run python project_tools/cleanup_merged_branches.py \
  --repo runchengxie/market-intel \
  --branch fix/example \
  --yes
```

钩子要求工作树 clean，且被推送 commit 等于当前 `HEAD`。紧急绕过可显式设置 `SKIP_LOCAL_CHECKS=1`，但仍会检查分支目标。绕过后应立即补跑完整门禁。

GitHub 端运行轻量的 Ruff、ty、离线契约测试和构建检查。完整 pytest、真实数据访问和部署验证仍由本地门禁或手动流程负责。纯数据 workflow 不受该策略影响。

## Owner 边界测试

本仓测试应重点覆盖：

- ETL、主题评分、市场资讯与降级行为
- artifact 日期、schema、hash 的安全失败校验
- DailyWatch20、D11-H5、style-factor 等 research-workspace artifact 的消费
- 报告渲染、图表、Dashboard 与受众隔离
- 飞书幂等、delivery receipt 和失败恢复
- scheduler/recovery 不安装或修复研究侧 timer
- `refresh_daily_watch20.sh` 只通过 `strategy-pipeline` 公开 CLI 恢复正式 artifact。

分钟因子研究、Hermite、walk-forward、OOS、ablation、AI ranking/shadow 等算法测试归 research-workspace owner，不在 market-intel 保留镜像测试。

## Linux/Hermes 运维测试

Gateway 守护与 systemd 模板使用 fake `systemctl` 或静态 shell 校验，禁止为了测试主动停止生产 Gateway：

```bash
uv run pytest tests/test_hermes_gateway_preflight.py
bash -n scripts/ensure_hermes_gateway.sh scripts/setup_cron.sh
```

部署后只做只读检查：

```bash
systemctl --user status hermes-gateway.service
systemctl --user status hermes-gateway-preflight.timer
systemctl --user list-timers --all
journalctl --user -u hermes-gateway-preflight.service --since today
```

生产 scheduler、主机安装和历史 research-only unit 清理属于私有 deploy 仓库。本仓测试只验证公开 CLI、契约和离线 fixtures。

## Windows 调度冒烟

不要通过修改主机系统时间测试 Task Scheduler。使用隔离的一次性任务：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\windows\test_scheduled_tasks.ps1 `
  -Kind morning `
  -DelayMinutes 2 `
  -Delivery none `
  -SkipAiNews `
  -SkipPremiumRefresh
```

默认不发送真实消息，产物写入隔离目录。测试真实投递必须显式启用发送并使用临时专用目标。

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
- 跨仓功能如果依赖 owner 改动，provider PR 和 research-workspace gitlink 必须先有可审计 commit。

通过 GitHub connector 创建的 PR 无法替代本机 `uv`/systemd/live-provider 验证。因此这类大规模边界迁移在真实本地门禁和部署 smoke 完成前应保持 Draft。
