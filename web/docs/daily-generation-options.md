# 每日生成与维护说明

初次核对日期：2026-09-25。2026-09-28 合并调整：`web/` 已纳入 `quant-intel-platform`，以下旧仓库运行记录按原始日期保留。当前发布入口与模型限制以[开发与数据维护](technical-guide.md)为准。

## 仓库职责与发布流程

| 仓库 | 职责 |
|---|---|
| `quant-intel-platform/web` | 导入明确可公开的报告，维护近期快照、来源核验和静态网站 |
| `quant-intel-platform` 平台模块 | 提供行情处理和报告生产能力 |
| `quant-intel-deploy` | 私有部署配置、生产定时器和恢复任务 |

平台与网页同属一个仓库，部署项目仍独立维护。`web/` 不是 submodule。数据和报告生产问题在平台模块修复，网页侧负责检查公开交接材料并准确显示状态。

当前统一网站工作流在 PR 中运行检查，在 `main` 推送或手动触发时构建和发布。它读取已提交的报告快照，不采集行情、不调用模型，也不读取本地私有报告。

六图交接使用 `market_intel.a_share_charts.v1`。上游 `chart-candidate` 只产生私有候选，不构成事实审核或公开授权；仅在逐点核对原始网页、日期、数值及使用许可后，独立签发带内容哈希且标明 `publication: public` 的清单，并附仓库外的逐点审核回执。Pages 侧核对回执、预览后导入，构建时只复制五个公开报告日期内的已审核 JSON，其他候选和旧 PNG 不会进入站点。2026-09-24 的新批次已产生候选，但尚无可公开清单；当前网页显示缺项是事实审核和许可门禁的结果，不再是等待下一次晨报生成。静态表保持无脚本可读，交互图按用户展开和当前报告 ID 加载。

受控发布器须先完成来源核验、解读与简评，再提交公开快照。统一网站工作流只校验并渲染该快照，确保 HTML 和公开 JSON 来自同一次提交。

网站侧现已提供报告准备入口，部署侧负责按交易日历调用并完成发布闭环：

美股日报与北京时间 19:00 的亚洲收盘复盘分别发布。旧版报告保留直达页供核对。首页历史区只收录从 2026-09-28 起的新版美股日报和亚洲晚报。平台从 Yahoo Finance 已完成的同日交易所日线取得四大指数收盘涨跌，四项不齐时整组缺项；优先使用美国财政部每日收益率表计算当日 bp 变动，缺失时才回退到 FRED；CPI、PCE、失业率和非农就业变动仍来自 FRED，逐项标注观测日。经逐条核实、与私有草稿哈希绑定的报道可补入市场解释与公司新闻，未通过审核的候选不进入报告；已核实的 AP 指数报道仍可作为人工审核来源。部署侧校验 JSON 后生成 `publication: public` 清单，独立美股 Pages 发布器才允许导入。首页、Markdown 与纯文本的主要行情顺序统一为指数及已核实重点个股、美债四期限水平和日变动、布伦特与金银及比特币；其他驱动、宏观和公司资料随后展开。没有审核材料的日子仍显示相应缺项。导入时由同一份公开白名单数据生成带来源 Markdown、无引用 Markdown 阅读版和纯文本版；构建时为最近五个公开美股报告日补齐阅读版。阅读版仅去掉来源链接、来源列和证据编号，不改事实、观测日与缺项；带来源原文仍可核查。两种 Markdown 均附公开质量状态，不包含私有核验底稿。Astro 首页将美股行情图解、已核实解读、经济数据和来源域名合为一张 SVG 图文复盘；亚洲晚报则按原有六图框架和市场状态、次日观察生成另一张图文复盘，缺项如实显示。网页只展示一份图文复盘，并保留完整报告及可点击的来源链接。两张图均在用户点击时从当前 SVG 生成 PNG；常规尺寸按双倍分辨率输出，长图会按画布上限缩放，不在仓库或 Pages 额外储存每日 PNG。首页美股下载入口只显示 Markdown 阅读版和图片版；带来源原文和纯文本公开产物仍保留在归档路径。

```text
行情来源与交易日历
  → 上游采集、数据就绪检查
  → 报告生成
  → 明确允许公开的 manifest
  → Pages 导入器：私有归档与近期快照
  → 模型解读与观察条件核验
  → 检查、PR、GitHub Pages 发布
```

报告缺失或时间无法确认时，保留缺项状态。新闻或模型解读不可用时，仍可发布已经验证的原报告。补发材料与重新生成的历史解读需要说明时间，供读者判断信息在当时是否可用。

## 09-19 初次盘点记录

以下记录描述当天维护开始时的状态，供排查和后续修复核对：

- Pages 仓库和完整归档的最新报告目标日期均为 09-14，索引更新时间为 09-15。网站部署成功，数据仍然落后。
- 服务器已有 systemd 用户定时器，分别在工作日 06:00 采集跨市场数据、17:30 刷新亚洲市场、18:00 发布 A 股 current 数据，并约每 45 分钟进行一次恢复检查。
- 恢复回执显示，`daily_market`、`minute_market`、`current_contract` 对 09-18 健康。`report_datasets` 为 `not_installed`，`morning_model` 为 `disabled_by_configuration`，`morning_report` 为 `disabled_dependency`，`evening_report` 为 `waiting_source_window`。
- `morning_model` 的停用来自部署仓库的显式配置。接回晨报前，需要确认停用该模型后的报告生产路径。
- 09-18 的 `morning_manifest.json` 为零字节，且没有对应 Markdown。上游 `morning_pipeline.sh` 直接重定向写入 manifest，命令失败时会先清空文件。部署侧需要查明失败原因，并改为临时文件生成、校验后替换。

既有采集任务应继续由部署侧维护。接入 Pages 时，重点补齐报告完成、允许公开和发布完成之间的交接记录。

## 模型运行记录

09-19 已配置仓库 Secret `GEMINI_API_KEY`。首次使用 `gemini-2.5-flash` 返回 `404 NOT_FOUND`，切换为 `gemini-3.8-flash` 后成功生成一条基于 09-14 材料的历史回放，来源引用与数字校验通过。详情见 [Actions 运行记录 35420008327](https://github.com/runchengxie/market-intel-pages/actions/runs/35420008327)。

原有短简评为 `chatgpt-reviewed` 人工审核样例。MiniMax 在线效果需要另行调用核对，不能从静态样例推断。

## 导入与核验

`scripts/refresh_reports.py` 调用已安装的 `a-share-daily` CLI，在仓库外准备报告。它不导入上游业务代码，也不触发消息投递。一次补发示例：

```bash
python3 scripts/refresh_reports.py \
  --owner-cli /path/to/owner/.venv/bin/a-share-daily \
  --data-root /path/to/market-data \
  --snapshot-root /path/to/cross-market-snapshots \
  --output-dir /path/to/staging/2026-09-18 \
  --date 2026-09-18 \
  --kind both \
  --generation-mode backfill
```

`--kind` 可选 `evening`、`morning`、`both`，默认只生成晚报。`--timeout-seconds` 限制整批调用，默认 180 秒。标准输出为包含 `manifest` 和 `errors` 的 JSON。原始诊断保存在外部私有批次目录，公开 manifest 仅在整批校验通过后原子替换，失败保留上一份有效清单。

晚报要求目标日期一致且存在真实成交与市场宽度数据。晨报要求同日期跨市场快照，拒绝以实时查询替代历史快照。当前新闻输入明确禁用，缺项在正文中说明。补发使用实际重建时间和 `backfill` 标记，正常调度使用 `scheduled`。

公开 manifest 由上游明确提供，只列允许公开的 Markdown。示例中的日期仅展示格式：

```json
{
  "schema_version": "market_intel_pages.import.v1",
  "publication": "public",
  "reports": [
    {"path": "evening.md", "date": "2026-09-18", "kind": "evening"},
    {"path": "morning.md", "date": "2026-09-18", "kind": "morning"}
  ]
}
```

路径相对 manifest 所在目录，文件需包含标题、正文和 `生成时间: YYYY-MM-DD HH:MM`，也支持秒与微秒，时间按北京时间解析。导入器检查路径边界、日期、报告类型和必需内容。重复相同输入不会更新索引时间。

在独立任务工作树中先预览：

```bash
python3 scripts/import_reports.py \
  --manifest /path/to/public/manifest.json \
  --archive-dir /path/to/private-archive
```

检查报告日期、内容和变更数量后应用：

```bash
python3 scripts/import_reports.py \
  --manifest /path/to/public/manifest.json \
  --archive-dir /path/to/private-archive \
  --apply
```

导入完成后检查数据状态，生成解读并构建：

```bash
python3 scripts/pipeline_health.py \
  --reports artifacts/public/data/reports.json \
  --expected-date YYYY-MM-DD \
  --strict
python3 scripts/generate_insights.py \
  --reports artifacts/public/data/reports.json \
  --history artifacts/public/data/insights.json \
  --output artifacts/public/data/insights.json \
  --archive-dir /path/to/private-archive
python3 scripts/build_site.py --output /tmp/quant-market-intel-check
```

`--expected-date` 应替换为上游交易日历给出的目标日期。未提供时标记 `calendar_unverified`，同时按原报告时间和目标日期结束时间检查 72 小时阈值。该结果描述数据年龄，完整的晨晚报到齐情况仍需结合报告类型与配对状态检查。

随后执行 [README 中的完整检查](../README.md#检查与维护)，提交公开快照，经 PR 合并后发布。生产任务应调用稳定发布目录中的入口。

## 调度与生产交接

报告准备入口使用 `a-share-daily evening --date YYYYMMDD`、`morning` 和 `morning-report`，不传 `--send-feishu`。网站发布任务直接检查日历、current 数据契约和数据健康回执，不依赖已停用的 `morning_model`，也不新增行情采集任务。

业务日期由上游交易日历提供。晨报目标日可能早于生成日，不同市场也可能处于不同交易日。06:00、17:30 等只是现有任务的触发时刻，报告截止时间需结合实际依赖确定。

这些调度职责由私有部署侧承担，导入器保持单次执行入口：

- 用业务日期、晨晚报类型、源内容哈希、提示词哈希和模型标识区分一次生成。
- 避免同一任务并发运行，在临时目录校验产物后发布 manifest。
- 保存各阶段状态、材料时间、产物哈希、重试次数和错误类型。
- 为重试设置次数、间隔与截止时间，并对迟到数据和补发报告留存回执。

## 调度方案取舍

| 方案 | 适用情况 | 需要承担的维护工作 |
|---|---|---|
| 复用本机 systemd 和单次流水线 | 当前数据、日志与凭据均在本地，便于补跑 | 持久化状态，处理休眠、网络和任务截止时间 |
| 报告就绪触发，配合定时对账 | 上游能提供完整 manifest，迟到数据需要及时补齐 | 定义完成标记和成功回执，避免读取写到一半的文件 |
| GitHub Actions 生成与发布 | 输入完全公开，或已有可供云端读取的产物 | 私有数据交接和定时任务延迟 |
| Prefect、Dagster 等编排服务 | 多市场、多受众和复杂回填已成为日常需求 | 额外服务、数据库、升级与运维 |
| 由 LLM agent 探索和写作 | 临时专题或异常事件分析 | 限定任务范围、成本和来源，保留确定性基础报告 |

现有环境适合复用本机调度，再补报告就绪触发和定时对账。GitHub Actions 的定时工作流可能延迟，公共仓库连续 60 天无活动时还会停用，参见 [GitHub 官方说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

## 解读生成与模型比较

结构化解读默认使用 `gemini-3.8-flash`。可选变量为 `GEMINI_MODEL` 与 `INSIGHT_PROVIDER`，后者接受 `gemini` 或 `minimax`。选择 MiniMax 时使用 `MINIMAX_API_KEY` 和 `MINIMAX_MODEL`。API 密钥在生成进程中读取。

生成器对限流、服务器错误和连接问题最多尝试三次，认证失败直接返回。公开诊断只包含错误类型、HTTP 状态码和白名单中的 API 错误代码。提供方输出形式参见 [Gemini 结构化输出文档](https://ai.google.dev/gemini-api/docs/structured-output)。

同一份历史材料可分别生成两家样本：

```bash
python3 scripts/compare_models.py \
  --reports artifacts/public/data/reports.json \
  --output-dir /path/to/private-comparison
```

脚本保存各提供方的运行状态、样本和人工审核问题。检查引用存在、数字来自引用、观察阈值来自已提取指标后，还需人工判断证据是否支持观点、因果是否克制、缺项是否说清，以及中文是否自然。积累约十个有效交易日的真实样本后，再评估是否更换默认提供方。

## 长期记录与观察条件

当前已保存材料来源、信息截止时间、生成时间、观点版本和独立的条件核验结果。补发材料以及生成时间超过材料截止时间三小时的解读标为历史回放，避免混入当时可用的前瞻记录。

观察条件使用晚报中可提取的指标作为阈值。后续首份符合日期和时间条件的晚报到来后，记录 `met`、`not_met`、`pending` 或 `unverifiable`。这些状态只表示条件是否成立，不能换算为投资收益或预测胜率。

本地 `--archive-dir` 以追加方式保存 `insights`、`outcomes` 和 `report_revisions`。解读归档还保存报告快照与核验来源，使离开公开窗口的旧观点能够继续核对。报告修订保留旧版本，结果变化另存回执。

Actions 上传的解读与结果 artifact 保留 90 天，作为中转备份使用。生产发布器会在部署成功后下载 artifact，写入 `/home/richard/code/.research-data/quant-market-intel-archive/pages_ledgers/`，并用 `archive-receipt.json` 核对文件哈希。当前已归档 9 月 19 日的多次发布回执，Actions 只作为中转来源。

早期讨论参考了 [MaiBot](https://github.com/Mai-with-u/MaiBot) 在自然表达和长期交互方面的思路。当前项目只实现报告来源、解读版本和条件结果的长期保存。主题检索、相似案例与反例召回、独立风格偏好，以及异常事件点评仍属后续方向。
