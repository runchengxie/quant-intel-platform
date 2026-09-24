# 市场日报 shadow run

`dm daily-report` 现从 FRED 获取美国宏观指标与美债收益率，生成带来源的 JSON 产物。设置 `API_KEYS_PATH` 指向私有凭据文件后，在美股交易日收盘后运行：

```bash
API_KEYS_PATH=/path/to/private/api_keys.json dm daily-report --date YYYY-MM-DD --out out/daily_report
```

`--date` 通常为运行时的美东日期。次日美东 09:30 前可携带已审核草稿与决定重建前一交易日的日报；更早日期不支持实时回放，因为当前接口不能证明旧日报截止时点已发布哪些修订值。

报告包含 2、5、10、30 年美债收益率最新日变动，以及 CPI 和 PCE 同比、失业率、非农就业月变动；收益率优先使用美国财政部每日数据，缺失时回退到 FRED。FRED 收益率可能比报告日期晚一个交易日更新：此时事实与 `rates` 来源状态标为 `lagged`，正文必须显示 `observation_date`，不得写成当日收盘收益率。`observation_date` 是序列观测日期，`source_time` 是本次读取来源的时间；这两个时间不能混用。指数行情及研究解释仅在审核通过的来源存在时补入，否则缺项写入 `missing_sources`。缺少数据时不填入示例数值。

检查 `daily_report.json` 的 `schema_version`、`as_of`、`content_hash`、`source_status`、`quality_summary`、各事实的 `source_url` 和 `observation_date`。发布端必须拒绝 `fixture` 状态或缺少核心宏观事实的产物，校验错误时保留上一份有效产物。

后续再接市场行情、公布日程与预期值、证据化研究解释。Pages 只读取通过校验的公开 `daily_report.json`。

## 联网研究草稿（内部待审）

已登录 Codex CLI 的机器可以运行：

```bash
dm research --date YYYY-MM-DD --out /path/to/private/research
```

`--date` 是美东交易日，而不是文章发布日期。复盘特定信息截止点时加上带时区的 `--cutoff`，例如 `--cutoff 2026-09-19T01:00:00+00:00`；不传时取本次运行时间。Codex 会实时联网搜索并在仓库外生成唯一命名的 `web-research-*.json`，对应运行回执存于输出目录的 `receipts/`。生成失败或 JSON 无效时不覆盖旧草稿。

草稿按市场表现、市场驱动、宏观、公司新闻、上涨个股和下跌个股归类。搜索优先覆盖收盘后的市场复盘与多家公司的原始公告或监管文件；找不到可靠来源时留空，不凑条数。盘中报道不能冒充收盘解释，模型也不能把股价同向变化写成已证实的因果。系统过滤交易日不符、来源晚于截止时间、无效 URL 或缺少支持段落的候选。**通过这些机器检查不代表网页内容已核实**：所有候选均为 `needs_review`，时间戳、数字、公司陈述和媒体解释仍需与原网页逐条核对，审核决定须绑定不可变草稿 SHA。此命令不会修改 `daily_report.json`，不会触发 Pages 或消息发布。生产调度应在部署仓库配置，使用稳定发布目录和仓库外输出路径。
