# Quant 生产行为等价设计

日期：2026-09-09  
适用范围：晨报、晚报、DailyWatch20、周报、交付回执、watchdog、调度与数据边界

## 1. 目标与非目标

目标是把当前私有生产 Quant 的可观察行为迁移到新的公开 `main` 架构，并在切换
前用同一输入双跑证明等价。等价指外部契约、业务字段、产物清单、日期身份、发送
幂等和失败语义一致；不要求复刻旧仓库的目录结构、私有 release 历史或内部实现。

本设计不重新启用已退休的旧 hotsector owner、legacy AI stock picker 或
`research-workspace` / 旧 `market-intel` 的 production owner 身份。私有生产线在
观察期内只作为只读回滚 archive。

## 2. Owner 边界

| Owner | 负责内容 | 不负责内容 |
|---|---|---|
| `quant-intel-deploy` | systemd/Hermes 入口、环境路径、调度、恢复、生产隔离 | 报告业务逻辑和策略模型 |
| `quant-intel-platform` | 报告生成、manifest、图表、delivery receipt、watchdog 契约 | 策略训练和原始数据采集 |
| `quant-research` | DailyWatch20、风格因子、D11-H5 和研究产物 | Feishu 路由和正式报告发送 |
| `quant-market-data-platform` | canonical 数据根、版本化资产、freshness 和数据 receipt | 业务报告渲染 |

生产入口只能通过 versioned artifact、JSON/Parquet/Markdown receipt 或公开 CLI
跨 owner 传递数据。任何入口都必须使用 canonical paths env，禁止从 retired
workspace 推导路径。

## 3. 运行输入契约

每次报告运行必须形成如下运行身份：

```json
{
  "source_date": "YYYYMMDD",
  "signal_date": "YYYYMMDD",
  "data_snapshot_id": "stable identifier",
  "code_revisions": {
    "market_intel": "git revision or release tag",
    "research": "git revision or release tag",
    "data_platform": "asset receipt revision"
  },
  "delivery_mode": "deliver|audit_only|dry_run",
  "run_id": "unique runtime identifier"
}
```

`source_date` 是业务数据所属交易日，`signal_date` 是运行/信号日，二者不能用
文件 mtime 互相替代。`data_snapshot_id` 必须能定位所有外部输入：A 股数据分区、
cross-market snapshot、研究产物和配置；同一 parity 双跑必须使用相同 ID。

历史重放不得把“当前 latest 分区”当作历史快照。实现应支持显式 as-of 输入根，
并在 receipt 中记录每个 dataset 的 as-of date、版本、路径和 freshness 状态。

## 4. 产物契约

### 4.1 晨报

晨报必须产生：

- `morning_manifest.json`
- `morning_report.md`
- 图表 bundle 和 `cross_market_summary.md`
- 每个启用产品的 delivery receipt

manifest 至少包含 `pipeline=morning`、`report_kind=morning`、业务日期、freshness
明细、topic summary 状态、cross-market 结构化字段和 chart/artifact inventory。
可选数据缺失必须成为显式 degraded/skipped 字段；不能改写业务日期或静默编造事实。

### 4.2 晚报

晚报必须产生 typed evening manifest、review/report、图表 bundle、MDP evening
receipt 和 delivery receipt。MDP receipt 不通过时，晚报可以 audit-only 结束，但
不得报告为成功发送。

### 4.3 DailyWatch20

研究 owner 产生 versioned run directory、`latest` alias、`watchlist_20.csv/json`、
candidate scores、model metadata、topic summary 和 `selection_receipt.json`。
receipt 必须能验证 source/signal date、模型/feature identity、symbol count、
provider 和输入 freshness。旧路径不得成为新 owner 的隐式 fallback。

### 4.4 周报与风格因子

周度产物使用 versioned style/research artifact，并记录 source date、owner revision
和输入 receipt。周报缺少增强数据时必须保留明确降级状态，不能把空结果伪装成完整结果。

## 5. 失败、恢复与交付语义

入口按以下顺序处理失败：

1. mandatory input、日期身份或核心 freshness 失败：退出非零，不发送。
2. optional input 失败：产出 degraded 字段，只有在产品契约允许时继续。
3. 生成成功但 receipt 缺失或日期错误：视为失败，不得依赖子进程退出码推断成功。
4. late recovery 默认 `audit_only`；只有显式 `MARKET_INTEL_FORCE_REPORT_DELIVERY=1`
   才允许历史补发。
5. 相同 kind/source_date/signal_date/content identity 的重试必须复用已有逻辑交付，
   不重复发送 Feishu 消息。

成功 receipt 至少包含：`kind`、`trade_date`、`signal_date`、`generated_at`、
`success`、目标 route 状态和 message IDs。watchdog 只信 canonical receipt 和
validated artifact，不信日志中“send succeeded”的文本。

## 6. Parity 方法

### 6.1 比较对象

比较器只读取两个已物化的 artifact roots，不在比较器内偷偷刷新数据。每次运行
写出一个 dated manifest，记录：

- source/signal date；
- old/new code revision；
- old/new data snapshot ID 以及是否相同；
- mandatory artifact inventory、缺失项和递归字段差异；
- receipt identity、status、route 和 message-id 差异；
- `unexplained_differences`。

默认只忽略运行时生成的 `generated_at`、`message_id`、`message_ids` 和 `run_id`。
环境路径只能在明确声明的 `paths` 映射或通过 `--path-field` 指定的映射下按 basename
比较；不能使用宽泛 ignore 规则隐藏业务字段。

### 6.2 快照要求

双跑开始前必须冻结并记录：

- canonical data root 的资产 receipt/hash；
- cross-market exact-date snapshot；
- DailyWatch20 selection/topic artifact；
- 配置和 owner revisions。

若 old/new snapshot ID 不相同，比较器退出非零，该日期不得计入五日门槛。live
外部数据在两个进程之间漂移时，必须回到冻结输入重跑，不能把数值 tolerance 当作替代。

历史 replay 的 freshness 证据可使用 `A_SHARE_FRESHNESS_SNAPSHOT`，输入一个
`a_share.freshness.snapshot.v1` JSON receipt。receipt 必须包含与目标日期一致的
`target_date`、完整 `datasets` 和 `contracts`，并具有稳定的 `snapshot_id`。
加载器对 schema、目标日期和结构执行 fail-closed 校验；未设置该变量时仍走生产的
canonical freshness 检查。该 receipt 只冻结 freshness 证据，实际数据文件仍必须由同一
`data_snapshot_id` 的数据目录/receipt 提供，不能用 freshness receipt 掩盖数据内容差异。

### 6.3 差异分类

每项差异必须属于以下之一：

- `environment`: 仅运行根路径或生成时刻；可通过显式归一化处理；
- `input`: 快照、as-of 日期或 provider 不一致；必须重新冻结；
- `contract`: 产物缺失、字段/日期/receipt 语义不同；需要代码或契约修复；
- `expected_retirement`: 明确列入 inventory 的退休功能；不得恢复；
- `unexplained`: 尚未分类；阻止 parity 通过。

只有 `environment` 已按规则归一化且不存在 `input`、`contract`、`unexplained`
差异时，运行才是 clean。

## 7. 调度和生产切换

所有 active systemd/Hermes unit 必须从 canonical paths env 解析：

- `MARKET_INTEL_DEPLOY_ROOT` 指向 deploy main checkout；
- `DATA_PLATFORM_ROOT` 指向 canonical data root；
- `MDP_DIR` 指向 market-data-platform runtime checkout；
- research owner 指向 quant-research main/release artifact；
- 不出现 retired workspace、旧 market-intel 或历史 release 目录。

切换顺序为：shadow no-send → 单产品 canary → postflight → 连续观察。canary
必须验证产物、receipt、watchdog 和 Feishu route；失败时回滚到前一已验证 release，
不得直接回到未经验证的 dirty checkout。

## 8. 完成门槛

项目只能在下列条件全部满足时标记 cutover：

1. inventory 中所有非 retired 项均有 contract、dual-run 和 verified 证据。
2. 至少连续五个交易日使用相同 data snapshot 语义，均无 unexplained mandatory 差异。
3. 晨报、晚报、DailyWatch20、周报和 watchdog 的正常、失败、恢复路径均有证据。
4. 发送回执、幂等重试和 audit-only late recovery 经真实链路验证。
5. 所有生产 unit 已解析到新 main/release；私有线只读归档且可完成 rollback rehearsal。
6. cutover 文档记录 commit、snapshot、unit audit、delivery audit 和回滚结果。

在这些条件满足前，任何“新框架已上线”的表述只能指 scheduler/path 已切换，
不能指行为 parity 或项目完成。
