# 市场日报 shadow run

`dm daily-report` 现从 FRED 获取美国宏观指标与美债收益率，生成带来源的 JSON 产物。设置 `API_KEYS_PATH` 指向私有凭据文件后，在美股交易日收盘后运行：

```bash
API_KEYS_PATH=/path/to/private/api_keys.json dm daily-report --date YYYY-MM-DD --out out/daily_report
```

`--date` 必须是运行时的美东日期。历史日期暂不支持实时抓取，因为当前接口不能证明旧日报截止时点已发布哪些修订值。

报告包含 FRED 的 2、5、10、30 年美债收益率最新日变动，以及 CPI 和 PCE 同比、失业率、非农就业月变动。FRED 收益率可能比报告日期晚一个交易日更新：此时事实与 `rates` 来源状态标为 `lagged`，正文必须显示 `observation_date`，不得写成当日收盘收益率。`observation_date` 是序列观测日期，`source_time` 是本次读取来源的时间；这两个时间不能混用。市场一致预期、指数行情及研究解释尚未接通，`quality_summary` 因此保持 `degraded`，缺项写入 `missing_sources`。缺少 FRED 数据时不填入示例数值。

检查 `daily_report.json` 的 `schema_version`、`as_of`、`content_hash`、`source_status`、`quality_summary`、各事实的 `source_url` 和 `observation_date`。发布端必须拒绝 `fixture` 状态或缺少核心宏观事实的产物，校验错误时保留上一份有效产物。

后续再接市场行情、公布日程与预期值、证据化研究解释。Pages 只读取通过校验的公开 `daily_report.json`。
