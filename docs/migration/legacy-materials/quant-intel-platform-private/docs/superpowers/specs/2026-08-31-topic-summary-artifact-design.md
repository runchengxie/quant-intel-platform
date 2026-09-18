# DailyWatch20 Topic Summary Artifact Design

## Goal

用 DailyWatch20 生产链路消费的同一份 `ths_hot` 输入生成可追溯的主题汇总，替代已经退休的 `hot-sector-screener` 对 `candidate_universe.json` 的依赖，并让晨报图表与 watchdog 对该输入保持一致。

## Scope and ownership

- `research-workspace/strategy-pipeline` 负责从 DailyWatch20 已准入的候选池生成并发布 `topic_summary.json`。
- `market-intel` 只校验、消费和渲染该 artifact，不重新计算股票热度或策略排序。
- 旧 `hot-sector-screener` submodule 不恢复，旧 `candidate_universe.json` 不再作为默认生产输入。

## Artifact contract

每个 DailyWatch20 run 目录发布一个 `topic_summary.json`，并在 `selection_receipt.json` 的 `artifacts` 中登记文件 hash。JSON 使用以下结构：

```json
{
  "schema_version": "daily_watch20.topic_summary.v1",
  "artifact_type": "daily_watch20_topic_summary",
  "source_date": "20260828",
  "signal_date": "20260831",
  "source": "daily_watch20.watchlist_20",
  "aggregation": "selected_watchlist_theme_count_and_weight",
  "topics": [
    {
      "topic": "半导体与电子",
      "count": 3,
      "weight": 0.35,
      "rank": 1
    }
  ],
  "quality": {
    "status": "passed",
    "selected_count": 20,
    "topic_count": 5
  }
}
```

`weight` 是入选股票 `tracking_weight` 按主题聚合后的权重，不能解释为全市场概念热度。消费侧图表标题和副标题必须使用“DailyWatch20 热点主题分布”这一语义。

生产方必须拒绝以下情况并让 DailyWatch20 run 失败：source/signal 日期缺失或非法、入选股票为空、主题为空、股票权重不是有限非负数、主题权重总和与入选股票权重总和不一致超过 `1e-9`。主题按照 `weight` 降序、`topic` 升序确定 rank。

## Publication and consumption

- `topic_summary.json` 与 `watchlist_20.json` 位于同一个 immutable run 目录。
- `latest` 通过现有发布机制指向包含该文件的 run。
- `market-intel` 默认从 `WATCHLIST20_ROOT/topic_summary.json` 读取，也允许 `A_SHARE_TOPIC_SUMMARY_INPUT` 显式覆盖，便于人工预览和恢复。
- 消费侧校验 schema、日期、artifact type、主题非空、权重有限且非负，并在可用时校验 `selection_receipt.json` 中的 hash。
- 缺失或校验失败时，晨报继续生成占位图并记录降级原因；不会阻塞正式晨报。

## Watchdog behavior

现有 DailyWatch20 producer/artifact watchdog 增加 topic artifact 检查，但默认关闭必需门禁：

- `WATCHDOG_REQUIRE_TOPIC_SUMMARY=0`：只输出 topic artifact 状态，不因缺失或异常退出非零。
- `WATCHDOG_REQUIRE_TOPIC_SUMMARY=1`：在已确认交易日检查 topic artifact 的日期、schema、非空主题和 receipt hash；失败时与 DailyWatch20 artifact 异常同样告警并返回非零。

检查必须使用 `WATCHLIST20_ROOT` 的实际 `latest` 路径和数据湖推断的 source date，不能检查开发目录、旧 hotsector 目录或历史缓存。

## Compatibility and rollout

第一阶段保留 manifest 的 `universe_json` 字段但不再把它作为新 topic 图输入；新增 `topic_summary_json` 字段。旧字段只有在显式配置且新 artifact 不存在时才允许作为人工兼容输入，默认生产路径不回退到旧候选池。

生产方先合入并发布 artifact，消费方随后合入并发布。若生产方尚未发布新文件，market-intel 以占位图降级；开启 `WATCHDOG_REQUIRE_TOPIC_SUMMARY=1` 前必须确认生产版本已包含该文件。

## Testing

- strategy-pipeline：主题聚合、排序、权重守恒、空主题/非法权重拒绝、run artifact 和 receipt hash 登记。
- market-intel：新 artifact 解析与校验、topic 图语义、缺失降级、manifest 字段和显式路径兼容。
- watchdog：默认可选时缺失不告警，必需模式下缺失/错日期/hash 错误告警，正常 artifact 通过。
- 使用两个仓库各自已有的单元测试与 lint/typecheck 入口；不把研究仓库测试接入 market-intel。
