# 市场日报网站

[English page](market-site.en.md)

[打开市场日报](https://runchengxie.github.io/quant-intel-pages/)。Pages 网站展示最近五个有报告的日期、来源和可下载报告。报告生成与审核由本仓负责；Astro 页面、静态渲染、托管和线上新鲜度监控由独立的 [`quant-intel-pages`](https://github.com/runchengxie/quant-intel-pages) 仓库负责。

本仓的 `market_intel_publication` 校验报告和版本化公开数据契约，再导出 Pages 可消费的快照。`quant-intel-deploy` 负责生产发布、回执和恢复。公开网站只读取已审核并标记为公开的产物。

亚洲报告索引为 [reports.json](https://runchengxie.github.io/quant-intel-pages/data/reports.json)，美股日报索引为 [market_daily_report.json](https://runchengxie.github.io/quant-intel-pages/data/market_daily_report.json)。完整配置、发布状态和恢复步骤见 Deploy 仓库的[市场日报发布手册](https://github.com/runchengxie/quant-intel-deploy/blob/main/docs/market-pages-publisher.md)。
