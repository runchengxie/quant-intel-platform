# 市场日报网站

[打开市场日报](https://runchengxie.github.io/quant-intel-platform/)。网站每天按北京时间 07:00 美股收盘、19:00 亚洲收盘两个时段组织内容。页面展示最近五个有报告的日期，具体以实际生成时间、观测日和缺项提示为准。

日报与本文档共用暖色设计语言，两边都可切换浅色和深色。首次访问会参考设备的外观设置；日报首页按指数、个股、美债和跨资产分组，指数小图只使用观测日与报告日一致的公开数据。

网站代码、构建工具和公开快照都在本仓的 `web/`。生产定时任务和密钥由私有部署仓库管理。公开 GitHub Actions 只校验已提交的数据并构建页面，不抓取带凭据的数据，也不调用模型。

## 本地预览

准备 Python 3.11 至 3.13、Node.js 24 和 npm，在仓库根目录运行：

```bash
cd web
npm ci
preview_root=$(mktemp -d /tmp/qmi-preview.XXXXXX)
python3 scripts/build_site.py --output "$preview_root/quant-intel-platform"
python3 -m http.server 8000 --directory "$preview_root"
```

打开 <http://localhost:8000/quant-intel-platform/>。构建器会重新创建指定输出目录，不要把业务资料目录作为 `--output`。

## 内容从哪里来

- `web/artifacts/public/` 保存完成公开审核的近期数据和报告。构建后下载路径仍是 `/data/`、`/reports/`。
- `web/src/` 负责 Astro 页面和旧版归档页面。`web/tests/` 覆盖契约与渲染。
- 平台包的 `market_intel_publication` 负责报告导入与公开快照，`market_intel_commentary` 负责模型解读。`web/scripts/` 保留兼容入口、图表审核与静态构建。市场数据权威资产及生产调度不在此处。
- 亚洲收盘解读先尝试本机 Codex，再按已配置密钥尝试 DeepSeek、Gemini、MiniMax。连续晚报可用最新晚报与前次晚报形成对照。历史晨晚报配对仍可阅读。

私有部署的配置、回执和恢复步骤在 `quant-intel-deploy/docs/market-pages-publisher.md`。网站内部的开发细节见 [`web/docs/technical-guide.md`](https://github.com/runchengxie/quant-intel-platform/blob/main/web/docs/technical-guide.md)。

## 线上快照新鲜度

公开网站的亚洲晚报索引是 [reports.json](https://runchengxie.github.io/quant-intel-platform/data/reports.json)，美股日报是 [market_daily_report.json](https://runchengxie.github.io/quant-intel-platform/data/market_daily_report.json)。检查应在运行时读取这两个线上 JSON，分别核对最近报告的市场日期和原始生成时间；静态构建时的健康信息不能代表当前状态。

任一报告超过 96 小时、快照无法读取或时间字段无效时，需要人工核查。96 小时只是保守提醒阈值；长假或其他休市可能触发提醒，不能据此断言发布失败，也不应阻塞网站部署。
