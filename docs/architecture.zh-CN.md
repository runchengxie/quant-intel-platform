# 系统架构

[English page](architecture.md)

quant-intel-platform 包含全球市场数据和 A 股报告流水线。它们共享运维工具和产物契约，各自的职责和故障边界保持明确。

## 流水线边界

```text
来源数据
-> 抓取与归一化
-> 事实 / 事件 / 研究产物
-> schema、日期、新鲜度与哈希校验
-> 报告组装
-> 公开快照 / 投递回执
```

`daily_messenger/` 负责全球市场 ETL、主题评分、报告、看板及 `dm` CLI。`a_share_daily/` 负责 A 股报告、已发布策略产物校验、图表和投递。`a_share_analysis/` 消费已发布研究结果，不新增研究算法。`tushare_jobs/` 是报告侧轻量兼容层，A 股权威数据由 `quant-market-data-platform` 管理。

平台通过 `market_intel_publication` 生成经过校验的公开报告快照。独立的 `quant-intel-pages` 渲染和托管日报网站。MkDocs 在 `/docs/` 发布平台文档，平台网站根路径保留到 Pages 的兼容重定向。

## 跨仓边界

研究和策略仓库通过公开 CLI 或版本化产物提供接口。quant-intel-platform 负责校验和展示这些产物，不导入 owner 业务源码，也不维护第二套实现。调度器、投递配置、凭据和真实运行状态由 `quant-intel-deploy` 管理。
