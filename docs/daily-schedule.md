# Market Intel 日内调度时间表

本文记录 `market-intel` 当前负责的报告、投递、数据准备和恢复任务。研究算法、因子实验、消融和策略生产逻辑由 `research-workspace` 负责。本仓只在必要时通过公开 CLI 恢复正式 artifact。

## 设计原则

1. 报告发送优先消费已经发布并通过日期/hash/schema 门禁的 artifact。
2. `market-intel` 不复制研究模型，也不通过旧 submodule 生成候选池或 AI 排名。
3. DailyWatch20 的策略由 `strategy-pipeline` / `strategy-app` 负责。本仓 05:20 的 producer 只负责调用公开 CLI。
4. 19:00 晚报前完成当日报告所需的数据刷新。19:00 后只做回填、次日早报和数据质量修复。
5. Gateway 自愈由 Gateway 外部的 systemd timer 执行。
6. freshness 以业务日期和 artifact receipt 为准，不以进程退出码代替。
7. 自动恢复有次数和冷却预算。发送前必须通过检查，已有成功发送但回执未对齐时不再次外发。
8. 研究侧 factor-observation、DailyWatch20 ablation、hotsector standalone 和 legacy AI freshness timer 已从本仓退休。

## 当前 Linux / Hermes 调度

| 时间 | 入口 | Owner 类型 | 作用 |
| --- | --- | --- | --- |
| 05:20 工作日 | `daily-watch20-producer.timer` → `refresh_daily_watch20.sh` | 运维桥 → research-workspace | 检查 DailyWatch20 输入和分钟级新鲜度，必要时补分钟数据，再调用 `strategy watchlist20 run/freshness` 发布正式 artifact |
| 06:00 / 06:45 | `local-fetch-cross-market.timer` | market-intel | 刷新跨市场快照，第二次为较晚更新的数据源补抓 |
| 06:40 工作日 | `a-share-morning-product-supervisor-preflight.timer` | market-intel | 检查正式 DailyWatch20/D11-H5 artifact 与同日恢复条件 |
| 06:50 工作日 | `hermes-gateway-preflight.timer` | market-intel | Gateway inactive 时启动并复检，健康时 noop |
| 07:00 工作日 | Hermes `morning_pipeline.sh` | market-intel | 校验并发送 DailyWatch20、D11-H5 和晨报，不运行旧 AI picker |
| 07:15 工作日 | `a-share-morning-product-supervisor-postflight.timer` | market-intel | 核对 artifact hash、delivery receipt 与幂等补发 |
| 17:30 | `asia-market-refresh.timer` | 数据桥 | 拉取/消费 A 股日线及亚洲收盘相关数据，为晚报准备事实层 |
| 18:00 | `a-share-current-publish.timer` | 数据桥 | 生成/验证 A 股 current 契约与报告输入 |
| 18:20 / 18:40 | `a-share-report-datasets-refresh.timer` | market-data-platform producer | 准备 TuShare 晚报数据并写入日期化 receipt |
| 18:50 工作日 | `hermes-gateway-preflight.timer` | market-intel | 晚报前再次检查 Gateway |
| 19:00 工作日 | Hermes `evening_pipeline.sh` | market-intel | 发送亚洲盘后 / 美股盘前晚报 |
| 19:20 / 20:30 | `a-share-report-datasets-refresh.timer` | market-data-platform producer | 晚间回填与次日 freshness 修复 |
| 周六 08:15 | `a-share-style-factor-weekly-refresh.timer` | research-workspace producer bridge | 调用标准入口发布周度风格因子，本仓不实现因子计算 |
| 周六 09:00 | Hermes `weekly_recap.sh` | market-intel | 消费已发布周度研究产物并发送周报 |
| 开机后约 5 分钟，之后每 45 分钟 | `market-intel-scheduled-recovery.timer` | market-intel | 核对数据、报告输入、正式策略 artifact 和投递状态，并按允许列表做有限恢复 |

## 已退休的本仓任务

以下任务不再由 `market-intel` 安装、调度或自动恢复：

- `a-share-factor-observation-refresh.timer`
- `daily-watch20-ablation.timer`
- `hotsector-research-handoff.timer`
- `a-share-ai-stock-picker-freshness.timer`
- 三个历史 owner submodule 中的任何定时任务

`setup_cron.sh --layer2` 会主动 disable 并删除这些旧 user-unit 文件。研究需求应进入 research-workspace 对应 owner，而不是恢复旧 timer。

## DailyWatch20 生产边界

正式链路是：

```text
market-data-platform data / report inputs
        ↓
strategy-pipeline: strategy watchlist20 freshness/run
        ↓
versioned DailyWatch20 artifact + selection_receipt
        ↓
market-intel: validate → render → delivery_receipt → Feishu
```

`refresh_daily_watch20.sh` 仍位于本仓，是因为它同时承担本机 minute quota、scheduler recovery 和部署环境桥接。它不得实现候选池算法、模型训练、Hermite 研究或 ablation。

news heat 是可选研究输入。若指定日期的 artifact 已存在就直接消费。缺失时，market-intel 按 strategy-pipeline 的可选输入规则继续运行，不启动 `hot-sector-screener` 重建。

## 晨报发送窗口

Hermes 重启可能折叠错过的 recurring run。晨报和晚报脚本因此先判定 delivery window：

- 晨报允许约 06:30–09:15 的正式投递窗口
- 晚报允许约 17:30–23:30 的正式投递窗口
- 超出窗口时可以生成审计 artifact，但关闭外发
- 同一业务日已有成功外发证据但 receipt 尚未一致时，recovery 只记录 `delivery_unverified`，不再次发送。

具体窗口逻辑由 `ops_common.report_window` 和正式 delivery receipt 决定。

## 断电 / 停机恢复

关键 systemd timer 使用 `Persistent=true` 时，恢复启动后会补触发最近错过的任务。它不会逐日重放所有历史计划，也不会无限重试失败的 oneshot。

`market-intel-scheduled-recovery.timer` 额外执行业务日期 freshness DAG：

1. 核心数据与 current contract
2. 报告增强数据和跨市场输入
3. DailyWatch20 正式 artifact
4. 晨报和晚报 delivery receipt

研究侧 factor pipeline 已从正式 recovery specs 过滤掉。恢复器不会因为报告缺失而自行启动研究实验。

每个 stage 的自动恢复次数有限，并写入 `state/scheduled_recovery/<YYYYMMDD>.json`。`latest.json` 与 heartbeat 记录最新状态，失败告警按 fingerprint 去重。

## 手动恢复

报告数据异常时：

```bash
bash scripts/refresh_tushare_daily.sh YYYYMMDD
bash scripts/publish_a_share_current.sh YYYYMMDD
A_SHARE_ENABLE_TUSHARE_PREMIUM=1 bash scripts/refresh_tushare_report_datasets.sh YYYYMMDD
```

DailyWatch20 正式 artifact 需要恢复时：

```bash
WATCHLIST20_SOURCE_DATE=YYYYMMDD WATCHLIST20_SIGNAL_DATE=YYYYMMDD \
  bash scripts/refresh_daily_watch20.sh
```

只校验/投递已经发布的正式 DailyWatch20：

```bash
uv run python scripts/send_daily_watch20.py \
  --date YYYYMMDD \
  --signal-date YYYYMMDD \
  --dry-run
```

不要再运行历史 `run_daily_watch20_ablation.sh`、`refresh_a_share_factor_observation.sh` 或旧的 AI 选股和热点生产入口。这些入口已退休。

## 部署

```bash
export RESEARCH_WORKSPACE_ROOT=/path/to/research-workspace
bash scripts/setup_cron.sh --layer2
bash scripts/setup_cron.sh --layer3
uv run a-share-daily doctor --live
```

部署检查：

```bash
systemctl --user list-timers --all | rg 'hermes-gateway|scheduled-recovery|a-share|cross|asia|daily-watch20'
systemctl --user status hermes-gateway-preflight.timer
systemctl --user status market-intel-scheduled-recovery.timer
systemctl --user status daily-watch20-producer.timer
hermes cron list
```

研究侧定时和 experiment cadence 以 `research-workspace` / `strategy-research` 文档为准，不在本时间表重复维护。
