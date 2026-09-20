# 市场日报 shadow run

平台首期只生成 shadow 产物，不修改生产定时器或页面发布。运行：

```bash
dm daily-report --date YYYY-MM-DD --out out/daily_report
```

检查 `daily_report.json` 的 `schema_version`、`as_of`、`content_hash`、`source_status` 和 `quality_summary`。研究提供商失败时可以发布确定性事实，但必须保留 `research` 降级状态。校验错误时禁止覆盖上一份有效产物。

部署仓库接入时应固定平台版本，按 `fetch -> normalize -> events -> research -> validate -> render` 顺序执行，并保存每阶段回执。Pages 只读取通过校验的公开 `daily_report.json`。
