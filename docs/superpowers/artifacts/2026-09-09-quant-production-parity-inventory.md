# Quant 生产功能对齐清单

日期：2026-09-09  
基准实现：当前私有生产线 `quant-intel-platform` + `quant-intel-deploy`  生成目标：新的公开 `main` 兼容实现

## 使用方式

本清单是迁移的唯一功能目录。每项必须有：当前生产入口、输入与输出契约、失败行为、parity fixture、测试和切换状态。状态含义：

- `inventory`：已登记，尚未完成新 main 对齐。
- `contract`：接口和回执契约已冻结。
- `dual-run`：新旧实现已用同一输入双跑。
- `verified`：连续交易日验证通过，可进入灰度。
- `cutover`：生产已切换到新 main。
- `retired`：明确不再支持，不作为隐式删除处理。

当前实现进度：parity JSON artifact 的基础加载、递归差异比较、字段忽略和
集合型列表排序契约已在 `tests/parity/` 冻结；生产 fixture 仍需按各产品任务
逐项脱敏并录入，不能把 comparator 的绿灯误认为整体 parity 已完成。

## A. 生产调度与入口

| ID | 能力 | 当前正式入口 | 关键输出 | 状态 |
|---|---|---|---|---|
| OPS-001 | 晨报主流程 | `quant-intel-deploy/scripts/morning_pipeline.sh` | morning manifest、markdown、delivery receipt | inventory |
| OPS-002 | 晚报主流程 | `quant-intel-deploy/scripts/evening_pipeline.sh` | evening manifest、报告与回执 | inventory |
| OPS-003 | 晨间 preflight/postflight | `morning_product_supervisor.sh` | 产品健康状态、告警 | inventory |
| OPS-004 | 定时恢复 | `reconcile_scheduled_runs.sh` | recovery audit、告警 | inventory |
| OPS-005 | 当前资产发布 | `publish_a_share_current.sh` | current asset contract | inventory |
| OPS-006 | 日报增强数据刷新 | `refresh_tushare_report_datasets.sh` | dataset receipts/status | inventory |
| OPS-007 | 指数数据刷新与 freshness | `refresh_a_share_index_daily.py`、`check_index_daily_freshness.py` | freshness result | inventory |
| OPS-008 | Hermes/systemd 路径边界 | canonical paths env + user units | 可追溯运行根目录 | contract |

## B. DailyWatch20 与研究产物

| ID | 能力 | 当前正式入口/owner | 关键输出 | 状态 |
|---|---|---|---|---|
| DW20-001 | 新 quant-research 全市场生产者 | `refresh_daily_watch20_quant_research.sh` | versioned run、`latest`、selection receipt | dual-run |
| DW20-002 | TuShare 分钟数据解析 | market-data-platform research view | minute feature receipt | dual-run |
| DW20-003 | candidate pool 与模型训练 | quant-research pipeline | scores、model metadata、20 symbols | dual-run |
| DW20-004 | topic summary | quant-intel-platform consumer | topic summary artifact | inventory |
| DW20-005 | Watch20 Feishu 投递 | `daily_watch20_delivery.sh` | delivery receipt、message ids | verified |
| DW20-006 | Watch20 freshness watchdog | `check_daily_watch20_producer_freshness.sh` | notify/exit status | inventory |
| DW20-007 | 旧 hotsector producer | retired compatibility path | 不再作为生产 owner | retired |

## C. 晨报、晚报与周报内容

| ID | 能力 | 关键输入 | 关键输出/行为 | 状态 |
|---|---|---|---|---|
| RPT-001 | 晨报 manifest | daily assets、cross-market、Watch20 | 日期严格匹配的 manifest | inventory |
| RPT-002 | 晨报 markdown/render | manifest、news、topic summary | 结构化晨报 | inventory |
| RPT-003 | 晚报 manifest/review | evening data、daily assets | evening manifest/review | inventory |
| RPT-004 | 跨市场数据 | US/JP/KR/commodity snapshots | structured cross-market payload | inventory |
| RPT-005 | 市场温度/主题/资金流图表 | platform-owned datasets | chart bundle | inventory |
| RPT-006 | 周度风格因子 | quant-research style owner | versioned style artifacts | inventory |
| RPT-007 | 周报/weekly recap | index/style/research artifacts | weekly report | inventory |
| RPT-008 | weekly client basket | weekly basket inputs | dry-run/client delivery artifacts | inventory |
| RPT-009 | D11-H5 shadow | quant-research strategy artifacts | research-only receipt | inventory |
| RPT-010 | legacy AI stock picker | retired scheduled feature | 不重新启用 | retired |

## D. 数据、回执与可靠性

| ID | 能力 | 必须保持的语义 | 状态 |
|---|---|---|---|
| DATA-001 | canonical data root | 所有生产任务使用 `DATA_PLATFORM_ROOT` | contract |
| DATA-002 | research root boundary | 不从 retired workspace 推导路径 | contract |
| DATA-003 | TuShare premium datasets | 缺失/权限不足可审计，不静默伪造 | inventory |
| DATA-004 | current asset contract | 版本、as-of、resolved path 可验证 | inventory |
| DATA-005 | materialized/symlink receipt | 两种合法 alias 形态均可消费 | dual-run |
| DATA-006 | delivery receipt | kind、trade_date、signal_date、generated_at、success | contract |
| DATA-007 | idempotent delivery | 重试不重复发送 | inventory |
| DATA-008 | late recovery | 过期运行默认 audit-only，显式 force 才补发 | verified |
| DATA-009 | failure alerts | mandatory product failure 到达 watchdog target | inventory |

## E. 明确的非目标与退休项

- 不恢复旧 `research-workspace`、旧 `market-intel` 的 production owner 身份。
- 不把历史 release 目录当作运行时依赖。
- 不把已经明确 retired 的 AI stock picker、旧 hotsector owner 重新接回正式调度。
- 不要求新 main 复刻旧目录层级；只要求外部行为、契约、结果和失败语义等价。

## 完成门槛

每个非 retired 条目必须完成 `contract → dual-run → verified`。整个项目只有在以下条件同时满足时才允许 cutover：

1. 所有正式 scheduler 入口解析到新 main/新 Quant 根目录。
2. 晨报、晚报、Watch20、周报和 watchdog 的 parity fixtures 全部通过。
3. 至少连续 5 个交易日双跑无未解释差异。
4. 发送回执、幂等和失败告警均经过真实链路验证。
5. 私有生产线只保留为可恢复 archive，不再是 active owner。
