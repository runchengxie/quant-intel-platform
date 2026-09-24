# 美股日报来源复核

`dm research` 只生成仓库外的私有候选草稿，不会把新闻写入正式报告。草稿的 `accepted_count` 表示结构与日期检查通过，不表示原文已核实。

逐条打开原文核对数字、解释、报道时间和盘中／收盘口径后，在仓库外建立审核 JSON：记录 `market_date`、原草稿文件 SHA-256、审核人，以及每条候选的 `index`、`status` 和 `reason`。`status` 只能是 `approved`、`deferred` 或 `rejected`；通过的候选还需单独撰写 `approved_summary`。指数涨跌要逐项记录 `index_returns` 及对应 `index_evidence`（`reported_change`、原文定位），目前只接受 AP 原站或 ABC News 上的 AP 报道。草稿变化或有候选未处置时，正式报告拒绝导入。

当日的正式命令：

```bash
uv run dm daily-report --date YYYY-MM-DD --out /private/staging \
  --reviewed-draft /private/research/draft.json \
  --reviewed-decisions /private/research/review.json
```

纽约时间次日 09:30 前可用同一命令修订前一个报告日；必须同时提供草稿和审核单。修订报告保留原报告日，`as_of` 记录实际重新核实时间，`quality_summary.revision` 标记 `next_morning_rechecked`，`reviewed_source_cutoff` 记录新闻截点。它不是历史数据 vintage 快照；不可把次日才出现的材料说成前一日收盘时已可得。

收益率日变动优先取美国财政部同一交易日与前一观测日的官方 CSV；官方数据缺失才回退 FRED，并按原始观测日标记当日或滞后。财政部 CSV 不提供逐行发布时间，因此该来源的 `source_time` 记录本次读取时间，而非声称为官方发布时间。指数数字来自逐条复核的报道，不是可持续再发布的授权行情流。正式公开仍须经过部署仓库校验与 `publication: public` 清单，再由独立美股 Pages 发布通道导入。
