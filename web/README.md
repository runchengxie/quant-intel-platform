# Quant 市场情报

这是一个静态日报网站。早上看美股收盘，晚上 19:00 看一份亚洲市场收盘复盘。首页分别展示美股与亚洲市场的单张图文复盘，并支持下载 PNG；美股另提供 Markdown 阅读版。从 2026-09-28 起，历史报告按新版图文格式积累。旧版报告不再列在首页，已有直达链接仍可核对。图中标注观测日、来源和缺项。网页保留可点击的来源链接和完整报告。报告仅供研究参考。

[打开网站](https://runchengxie.github.io/quant-intel-platform/) · [平台文档](https://runchengxie.github.io/quant-intel-platform/docs/)

## 能看到什么

- 07:00 美股收盘复盘：指数、已核实重点个股、美债收益率及日变动、布伦特原油、金银和比特币行情。
- 19:00 亚洲市场收盘复盘：A 股与亚洲市场表现、六维观察、图表和次日验证。
- 首页美股入口提供 Markdown 阅读版与图片版；亚洲入口提供图片版和完整六图报告。带来源的原报告仍在完整报告及归档中可查。

页面的 07:00 和 19:00 是北京时间的发布目标，并不保证每次准点或每项数据齐全。请以页面显示的实际生成时间、观测日和数据状态判断新鲜度。五个日期的窗口也不表示五个交易日的数据都已齐全。

## 快速预览

准备 Python 3.11、Node.js 24 和 npm。从平台仓库的 `web/` 目录执行：

```bash
npm ci
preview_root=$(mktemp -d /tmp/qmi-preview.XXXXXX)
python3 scripts/build_site.py --output "$preview_root/quant-intel-platform"
python3 -m http.server 8000 --directory "$preview_root"
```

然后打开 <http://localhost:8000/quant-intel-platform/>。输出目录由 `mktemp` 新建；构建会重新创建指定目录，请勿改成存放业务数据的路径。只想检查 Astro 页面时，可运行 `npm run build`。

## 到哪里找

| 目录 | 内容 |
|---|---|
| `src/` | 正式 Astro 网站和 `/legacy/` 旧版回退页面 |
| `artifacts/public/` | 已审核、可公开的近期报告与数据，构建后仍以 `/data/`、`/reports/` 提供下载 |
| `scripts/` | 导入、校验、构建脚本及模型生成兼容入口；模型实现与提示词位于平台 `src/market_intel_commentary/` |
| `configs/` | 无密钥的配置样例，真实凭据放在仓库外 |
| `tests/`、`tools/` | 测试与结构审计工具 |
| `docs/` | 维护方法、数据契约和历史设计记录 |

`web/` 是 `quant-intel-platform` 的公开日报应用，不是独立仓库。报告刷新由 `market-public-refresh` 负责，模型解读由平台包的 `market-commentary` 负责。网页中的同名脚本暂作兼容入口。导入和快照脚本仍在 `web/`，后续按职责整理。生产发布与定时任务仍由独立的 `quant-intel-deploy` 管理。具体边界见[开发与数据维护](docs/technical-guide.md#项目边界)。

## 常见问题

为什么网页有缺项？报告只展示通过日期、来源和公开审核的字段。模型输出通过格式校验，不代表新闻事实已核实；缺少可靠材料时会保留空缺。

数据和报告为什么不直接放在网站根目录？`artifacts/public/` 是 Git 中的公开输入，构建器会把它们放到网站的 `/data/` 和 `/reports/`。因此下载网址没有增加 `artifacts/public/` 这一层。

如何导入报告或运行完整检查？参见[开发与数据维护](docs/technical-guide.md)、[每日生成与维护说明](docs/daily-generation-options.md)和[仓库协作约定](AGENTS.md)。六图的公开审核另见[审核记录](docs/chart-review-2026-09-25.md)。
