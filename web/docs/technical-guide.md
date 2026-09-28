# 开发与数据维护

本文放置日常阅读网站时不需要了解的技术细节。新同事先读[项目首页](../README.md)，需要导入、生成或发布报告时再查这里。生产任务由独立的 `quant-intel-deploy` 仓库管理，本文命令只用于本地验证和准备公开快照。

## 项目边界

`web/` 是 `quant-intel-platform` 内的公开日报应用，负责近期快照、公开校验、静态页面和 GitHub Pages 展示。平台 Python 模块负责行情与报告生产，独立的 `quant-intel-deploy` 负责生产定时器和发布。本目录不是 Git submodule。

长期目标是让 `web/` 专注公开展示。新数据抓取、研究解释、报告写作和模型编排放在平台模块。网站接收带版本、日期、来源及审核状态的公开产物，做发布前校验、静态渲染与下载。现有 `scripts/` 中的导入、简评和解读入口仍被发布器调用，迁移期间暂时保留。

迁移现有入口时，先由平台模块提供等价产物，再切换 deploy 调用，最后移除 `web/` 中的旧入口。各阶段都须验证历史报告和新报告可以展示。

公开窗口按实际存在的报告日期计算。只有晚报的日期也占一个名额。完整报告、历史解读和审核回执放在仓库外的私有归档中。Pages 构建或部署成功只说明网站可用，不代表数据及时或新闻事实已经核实。

## 本地预览

CI 使用 Python 3.11 和 Node.js 24。安装锁定的 Node 依赖后，先用 Python 校验公开快照，再生成 Astro 页面。输出目录必须是仓库外的专用目录，构建会重新创建它。

```bash
npm ci
preview_root=$(mktemp -d /tmp/qmi-preview.XXXXXX)
python3 scripts/build_site.py --output "$preview_root/quant-intel-platform"
python3 -m http.server 8000 --directory "$preview_root"
```

打开 <http://localhost:8000/quant-intel-platform/>。站点基址是 `/quant-intel-platform/`，报告下载和数据请求仍使用该基址下的 `/reports/`、`/data/`。`npm run build` 可单独检查 Astro 输出，其 `dist/` 仅供开发验证。正式页面和 `/legacy/` 回退页面都支持深色模式。首页的日期趋势只取最近五份公开日报中观测日等于报告日的指数事实，不足两期时不画趋势；每日行情图默认展开，归档筛选只作用于历史报告。平台文档构建到同一站点的 `/docs/`。

## 导入公开报告

在独立任务 worktree 中先预览公开清单。确认日期、来源、正文和改动范围后，再加 `--apply`。

```bash
python3 scripts/import_reports.py \
  --manifest /path/to/public/manifest.json \
  --archive-dir /path/to/private-archive
python3 scripts/import_reports.py \
  --manifest /path/to/public/manifest.json \
  --archive-dir /path/to/private-archive \
  --apply
```

导入器检查报告内容、生成时间和路径，保存修订记录，再更新最近五个报告日期的公开快照。清单格式和上游交接见[每日生成与维护说明](daily-generation-options.md#导入与核验)。已有索引需要归档或收窄公开窗口时，可运行：

```bash
python3 scripts/sync_public_snapshot.py --archive-dir /path/to/private-archive
```

归档目录与仓库必须分开且互不包含。修改已有报告时优先使用导入器保留修订。收窄当前快照不会删除公开 Git 历史中的旧副本。

## 模型生成

生产发布器在本机导入新报告后，通过平台包 `market_intel_commentary` 优先调用已登录的 Codex CLI 生成带证据的结构化解读和简评。CLI 在只读沙盒运行，登录态不上传到 GitHub。无效输出不会写入公开索引，也不会阻止原报告发布。旧 `web/scripts/generate_*.py` 暂作兼容入口，新调用方使用平台的 `market-commentary` 命令。

平台公开网站 workflow 只校验并展示已发布材料，不读取模型密钥。Codex 和备用模型的调用需在受控发布链路完成。当前本机发布器优先使用 Codex，Gemini、DeepSeek、MiniMax 的新链路尚待切换验证。模型输出通过格式校验不等于新闻事实已独立核实，不能补造缺少来源的公司新闻或市场归因。

| 用途 | 入口 | 依赖 |
|---|---|---|
| 本机默认解读 | `scripts/generate_codex_commentary.py` | 已登录的 Codex CLI、仓库外的工作和归档目录 |
| 每日简评 | `scripts/generate_daily_summary.py` | 有效解读概览，或 `MINIMAX_API_KEY` |
| 带来源的市场解读 | `scripts/generate_insights.py` | 受控环境手动运行，自动回退链路待迁移 |

配置样例是 `configs/.env.example`。实际密钥留在仓库外，通过受控进程环境传入，不进入公开网站 workflow。Richard 机器可沿用 `~/.config/richard/`，其他机器选择自己的私有配置目录，代码不固定用户名。以下路径是占位示例：

```bash
cp configs/.env.example /path/to/private/model.env
set -a; . /path/to/private/model.env; set +a
python3 scripts/generate_insights.py \
  --reports artifacts/public/data/reports.json \
  --history artifacts/public/data/insights.json \
  --output /tmp/quant-market-intel-insights.json \
  --archive-dir /path/to/private-archive
```

本地单独测试可以用 `--provider` 指定模型，`--force` 重新生成。源内容、提示词和模型共同决定缓存是否可复用。旧解读仍须留在归档。模型失败或材料未齐时，原报告保持可读，页面显示相应状态。

## 文件和数据契约

| 路径 | 用途 |
|---|---|
| `src/pages/`、`src/components/`、`src/lib/`、`src/styles/` | Astro 首页、逐期正文、图表和安全 Markdown 渲染 |
| `src/legacy/` | 旧页面回退材料，只发布到 `/legacy/` |
| `artifacts/public/data/`、`artifacts/public/reports/` | 已审核的五日期公开输入，构建后仍输出到网站的 `/data/`、`/reports/` |
| `configs/.env.example` | 空白配置样例，不保存真实密钥 |
| `scripts/`、`tests/`、`tools/` | 网站导入、构建、兼容入口、测试和结构审计工具；提示词位于平台 `src/market_intel_commentary/prompts/` |

报告索引使用 `market_intel_pages.reports.v1`。每条记录有 `id`、`date`、`kind`、`title`、`summary`、`sections` 和 `source_url`。`kind` 为 `morning` 或 `evening`，`source_url` 保持 `reports/<id>.md`。简评使用 `market_intel_pages.daily_summaries.v1`，记录目标日期、正文、晨晚报 ID、生成时间、模型和提示词版本。解读使用 `market_intel_pages.insights.v1`，记录材料截止时间、内容哈希、证据、观察条件和核验结果。

构建生成 `data/health.json`，分别计算原报告时间和目标数据日期的年龄。没有交易日历目标时标记 `calendar_unverified`，仍按默认 72 小时阈值提醒。Markdown 表格、列表和标题转换为页面结构，正文以文本节点显示，不执行报告内 HTML。

## 六图审核

六图由上游生成私有候选。审核人逐点核对来源网页、观测日、数值和公开展示许可，签发 `publication: public` 清单，并在仓库外填写与清单哈希绑定的私有回执。网址和回执存在只能证明流程完整，不能替代事实核实或法律判断。候选不会自动进入公开网站。

```bash
python3 scripts/chart_review.py \
  --source /path/to/reviewed-public-chart.json \
  --output /path/to/private-review.json
# 人工填写每个点值的 fact_url、fact_note、rights_url、rights_note、reviewer、reviewed_at。
python3 scripts/import_charts.py \
  --source /path/to/reviewed-public-chart.json \
  --review /path/to/private-review.json \
  --archive /path/to/private-archive
python3 scripts/import_charts.py \
  --source /path/to/reviewed-public-chart.json \
  --review /path/to/private-review.json \
  --archive /path/to/private-archive --apply
```

回执按内容哈希追加在私有归档的 `chart_reviews/<report_id>/<chart_sha256>/<review_sha256>.json`，不会覆盖旧复核。没有审核通过的清单，页面显示六张缺项卡。有审核的卡片在 HTML 中可读，交互图仅展开时加载当期 JSON 和绘图库。实际审核记录见[六图候选审核记录](chart-review-2026-09-25.md)。

## 检查与发布

提交前按 [AGENTS.md](../AGENTS.md) 的质量门禁运行 Ruff、ty、vulture、Python 和 Node 测试、独立站点构建、依赖审计、结构审计与 `git diff --check`。代码指标、已知缺口见[维护检查记录](maintenance-audit-2026-09-19.md)。页面改动还要检查默认日期、筛选、无数据、来源展开、桌面和手机布局、深色模式。

GitHub Actions 在 PR 上检查网页和平台文档，`main` 更新或手动触发时一次构建、一次部署。它只渲染仓库中通过公开校验的近期产物，不生成新解读。需要密钥的生成和私有归档留在受控发布链路。

09-15 的[网站设计](superpowers/specs/2026-09-15-quant-market-intel-pages-design.md)、[网站实施](superpowers/plans/2026-09-15-quant-market-intel-pages.md)与[MiniMax 实施](superpowers/plans/2026-09-15-quant-market-intel-minimax.md)保留早期决策背景，当前操作以本页、[每日生成与维护说明](daily-generation-options.md)和 [AGENTS.md](../AGENTS.md) 为准。
