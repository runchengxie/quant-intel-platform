# 海外主题研究证据消费

日报将研究证据与当日海外行情观察分开展示。回溯研究不构成当日预测，也不用于推荐 ETF。

文件契约为 `overseas_theme_evidence.v1`。[Schema 副本](contracts/overseas_theme_evidence.v1.schema.json)
原样来自研究 owner 的同名文件。每份产物通过 `source_revision` 记录研究源码版本，调用方另行
指定整个文件的 SHA-256。源码版本与文件摘要不能互相替代。

`research_contracts.overseas_theme.load_evidence(path, expected_sha256, observed_at)` 最多读取 2 MiB，
先核对摘要再解析 JSON，拒绝重复键。消费端检查必需字段类型、来源 ID 与摘要的一致性、HTTP(S)
链接、唯一证据 ID、有限误差改善值和有序区间。生成时间必须为 UTC，且不能晚于观察时点；样本
起止日期必须有序，结束日期不能晚于生成时刻对应的上海日期。源码版本须为完整的 40 位小写
Git 哈希。证据状态仅允许回溯探索，历史时点认证必须为 false。结果类型限 gap、post_open、
next_tradable_open；滞后限 0 或 1 个交易日。

`a_share_daily.overseas_theme_report.render_evidence` 展示全部比较，包括负改善值，以及样本日期、
生成时间、源码版本、证据 ID、来源链接与摘要、研究局限。它原样报告研究方结果，不重新计算。
MSE 改善为正表示误差下降；区间跨零不能证明改善。展示文本保存在模块内的中英文目录中，缺省为英文。

缺失或校验失败时，报告明确降级为观察信息。`EvidenceError` 继承 `ValueError`，字符串内容为稳定
原因码；调用方捕获后可交给渲染器，不展示本地路径和解析器细节。观察时间必须带时区，摘要必须
来自可信渠道；与不可信文件并列的摘要不能证明来源。消费端不抓取链接，也不独立认证源数据。

隔离验证命令：`uv run pytest tests/test_overseas_theme_evidence.py`。


## 晨报入口与观察口径

```bash
uv run a-share-daily morning-report --manifest /external/morning_manifest.json \
  --news /external/market_news.json --out /external/morning_report.md \
  --overseas-theme-evidence /external/overseas_theme_evidence.v1.json \
  --overseas-theme-sha256 <reviewed-artifact-sha256> --locale zh-CN
```

本地 manifest 也可提供 `overseas_theme_evidence: {"path": "...", "sha256": "..."}`；显式 CLI
参数覆盖该配置。渲染器始终重新核对文件字节，不信任预先填入的研究结论。缺失或错误会在报告中
显示降级原因。默认只生成报告，不发送消息。

默认时钟带时区，统一转为上海时间。观察截点取生成时刻与决策日 08:45 的较早者；输入数据日
不替代实际生成日期。历史重放须给 `render_morning_report` 提供明确的 `generated_at`。
报告按上交所日历区分盘前、盘中、盘后和休市；海外行情按各交易所最近已完成交易日校验，覆盖
节假日和夏令时。晨报流水线将截点传给行情选择；一般日线调用保留原有指定交易日口径。
来源收盘时间不能证明历史抓取时刻。尚无经审查的主题历史输入，因此目前不展示新的实证结论。

产业关联映射版本为 `overseas_concepts.v1`，保留原人工权重，明确作为描述性观察。
旧快照中的 bullish/bearish 不升级为当前预测，来源不足时标为未核验。没有持仓证据时不列 ETF。
非有限值、结构损坏、未来、缺日期和过期行情不计入截点下的映射；合格来源显示证据 ID、链接、
行情日期和收盘时间。

Schema 来源为 [quant-market-research f918f283](https://github.com/runchengxie/quant-market-research/blob/f918f2832938743bd743021a7dfd89590e6af002/docs/contracts/overseas_theme_evidence.v1.schema.json)，
SHA-256 为 `4282b0c855633a53096c2c9a7947cd27f761bac7498a2a0ba7e70144b85c883b`。
安装包内嵌 Schema，测试保证其与文档副本一致。跨仓只交换文件，不导入研究仓源码。

## 活跃晚报入口

`a-share-daily evening` 和 `review` 支持
`--overseas-theme-evidence PATH --overseas-theme-sha256 SHA256`。
部署默认值来自 `OVERSEAS_THEME_EVIDENCE_PATH` 和
`OVERSEAS_THEME_EVIDENCE_SHA256`，命令行显式参数优先。公开报告刷新调用该活跃
CLI，也会继承这些默认值。

Markdown 追加现有回溯研究章节，保留全部比较、来源与局限。JSON 的
`overseas_theme_research` 保存 `status`、`evidence_cutoff_utc`、`rejection` 和
`evidence`。未提供或校验失败时保留市场事实，明确显示研究不可用。
校验截止为实际生成时间与报告日期上海时区当日结束时间中的较早者，历史回填不能使用
之后生成的研究。这一章节保持回溯探索状态，不构成当日预测或策略晋升。
生成报告仍须显式提供既有投递参数才会发送消息。
