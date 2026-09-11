# 报告内容模型与可切换主题系统设计

**状态：待 review**  
**日期：2026-09-11**  
**范围：`quant-intel-platform`、策略/回测 artifact owner、`quant-intel-deploy`**

## 1. 背景

当前晨报、晚报、周报在不同模块中分别组装和渲染，内容结构与视觉样式存在耦合。周度十股推送已经验证了暖白 editorial 风格的可读性，但它目前主要是 Markdown 文本，缺少统一的主题接口和可靠的历史净值图输入。

本设计把报告分成内容模型、主题、渠道渲染和投递四层，使晨报、晚报、周报可以共享内容组件，同时保留深色终端主题、当前暖白主题和新的研究 editorial 主题。

## 2. 目标

1. 把报告内容和视觉风格解耦，主题可以独立切换。
2. 为晨报、晚报、周报提供统一的摘要、指标、清单、图表、说明和降级表达。
3. 保留现有报告业务逻辑、数据校验、投递幂等和受众隔离。
4. 支持同一份报告内容生成 Feishu Markdown 和 editorial PNG。
5. 为周报接入版本化的历史净值 artifact，缺失或失效时安全降级，不绘制假数据。
6. 保留历史深色风格，并通过配置选择主题。

## 3. 非目标

- 不在报告仓库重新实现行情抓取、因子计算、组合构造或回测。
- 不改变晨报、晚报、周报的业务内容和选股结果。
- 不把 Feishu 图片渲染改造成交互式 dashboard。
- 不在第一阶段迁移全球市场 `daily_messenger` 的全部 HTML 模板。
- 不把真实客户持仓、凭证或生产运行产物写入仓库。

## 4. 分层架构

```text
已发布数据 artifact / receipt
            ↓
现有报告内容适配器
            ↓
ReportDocument 内容模型
            ↓
ReportTheme 主题 token 与版式组件
            ↓
MarkdownRenderer / PngRenderer
            ↓
Feishu 文本、Feishu 图片、本地报告产物
```

### 4.1 内容层

新增轻量、不可变的内容模型，建议放在 `a_share_daily/reporting/`：

- `ReportDocument`：报告类型、报告日期、标题、摘要、章节、数据状态、免责声明。
- `ReportSection`：章节标题、说明和有序组件。
- `MetricGroup` 与 `Metric`：数值、单位、标签、状态和来源。
- `PositionList` 与 `PositionCard`：股票名称、代码、来源、状态、日期、排名和评分。
- `SeriesChart`：组合净值、可选 benchmark、单位、日期范围和数据来源。
- `Notice`：研究用途、shadow、数据降级和风险提示。

内容模型只接受已校验的值，不包含颜色、字体、像素位置和 Markdown 语法。

### 4.2 主题层

主题实现 `ReportTheme` 协议，至少提供：

- 颜色 token：`paper`、`surface`、`ink`、`muted`、`rule`、`accent`、`chart_primary`、`chart_benchmark`。
- 字体 token：标题衬线、正文无衬线、元信息等宽字体。
- 间距和尺寸：页边距、章节间距、卡片高度、图表高度、最大宽度。
- 语义样式：标题、指标、状态标签、股票卡片、表格、图表和免责声明。
- 主题元数据：主题名、版本、默认尺寸和可用渠道。

首期主题：

| 主题 | 用途 | 默认状态 |
| --- | --- | --- |
| `dark_terminal` | 历史深色客户端图 | 保留，可切换 |
| `warm_light` | 当前暖白报告 | 现有默认兼容 |
| `research_editorial` | 周报和研究型组合简报 | 新增试点 |

`research_editorial` 使用暖白纸张、衬线标题、低饱和策略色、细规则线和紧凑双列卡片。它不使用大面积纯色背景，也不让单一装饰色承担全部信息语义。

### 4.3 渲染层

渲染层只消费 `ReportDocument` 和 `ReportTheme`：

- `MarkdownRenderer`：输出 Feishu-safe Markdown，保留标题、列表、状态标签和降级说明。
- `PngRenderer`：使用 matplotlib 或现有图表基础设施生成固定尺寸 PNG，输出图片 metadata 和内容 hash。
- `LocalArtifactRenderer`：写入 `report.md`、`report.png`、`render_receipt.json`。

Feishu 投递层不参与内容判断。发送文本时使用 Markdown，发送图片时先上传图片获取 `image_key`，再发送图片或含图片的 post。任一渲染失败都保留文本产物并写入失败 receipt，不自动改发其他受众。

## 5. 报告类型适配

第一阶段只新增适配器，不重写已有业务逻辑：

| 报告 | 内容适配器 | 首选主题 | 迁移策略 |
| --- | --- | --- | --- |
| 周度十股 | `weekly_basket_document` | `research_editorial` | 先完整迁移 |
| 晨报 | `morning_document` | `warm_light` | 保持内容，替换渲染入口 |
| 晚报 | `evening_document` | `warm_light` | 保持内容，替换渲染入口 |
| 深色客户端图 | 现有内容适配器 | `dark_terminal` | 作为主题兼容层 |

周报的页面顺序为：

1. 日期、标题、截至收盘和研究用途。
2. 10 只股票、三类来源数量和组合状态。
3. 两列股票卡片，显示名称、代码、策略、状态、信号和有效期。
4. 新增、保留、剔除差分。
5. 有数据时显示历史净值图及四项收益指标。
6. 数据来源、shadow 和风险说明。

晨报和晚报先保持现有章节语义，只把章节、指标、图表和说明映射为公共组件。任何缺失数据沿用现有降级文案，不能因为主题切换而改变数据状态。

## 6. 历史净值 artifact 契约

净值生产属于策略/回测 owner，报告仓只消费版本化 artifact。推荐文件名为 `basket_performance.json`，而不是泛化的 `performance.json`，避免不同策略之间误用。

```json
{
  "schema_version": "weekly_basket.performance.v1",
  "report_date": "20260914",
  "series": [
    {"date": "20260901", "nav": 1.0000},
    {"date": "20260902", "nav": 1.0124}
  ],
  "benchmark": {
    "label": "沪深300",
    "series": [
      {"date": "20260901", "nav": 1.0000},
      {"date": "20260902", "nav": 1.0041}
    ]
  },
  "source": "portfolio-backtester",
  "artifact_sha256": "..."
}
```

契约要求：

- 日期升序、无重复、格式为 `YYYYMMDD`。
- 净值为有限正数，首个点必须可归一化为 1.0。
- 组合序列的最后日期不得晚于报告日期。
- benchmark 可选，缺失时只画组合单线。
- 生产 artifact 必须带 schema、来源和 SHA-256 receipt。
- 数据缺失、过期、hash 不匹配或序列不足两个点时，不画图，报告明确写“历史净值数据不可用”。

跨仓顺序为：回测/策略 owner 先产出和发布契约，`quant-intel-platform` 再消费，最后由 `quant-intel-deploy` 增加显式输入路径。报告仓不能自行补抓行情或重算收益。

## 7. 主题切换接口

CLI 和部署层统一使用显式主题参数：

```bash
a-share-daily morning --theme warm_light
a-share-daily evening --theme research_editorial
a-share-daily weekly-basket --theme research_editorial
```

环境变量 `REPORT_THEME` 只作为未提供 CLI 参数时的默认值。非法主题必须 fail closed，并列出可用主题。默认值保持当前生产行为，避免历史调度静默换版。

每次渲染 receipt 记录：

- report type 和 report date
- theme name 和 theme version
- renderer name 和 renderer version
- 输入 artifact path/hash
- 输出文件 path/hash
- Markdown/PNG 是否生成
- Feishu 发送状态和 idempotency key

## 8. 测试策略

### 内容模型

- 正常报告由章节、指标、清单、图表和说明组成。
- 缺失可选章节不影响其他章节。
- 无效日期、负数净值、重复日期和不一致 benchmark fail closed。

### 主题和渲染

- 同一 `ReportDocument` 切换主题不改变内容值和顺序。
- 三个主题都能生成 Markdown；支持图片的主题生成 PNG。
- 主题 token 完整，不能出现未定义颜色或字体。
- PNG 尺寸、背景色、标题和图表标签有快照或结构化断言。
- 生成失败时不发送图片，不影响本地 Markdown 保存。

### 报告迁移

- 晨报和晚报旧内容关键段落仍存在。
- 默认主题生成结果与迁移前的内容契约一致。
- 周报的新增、保留、剔除统计与 canonical basket 一致。
- 有净值时生成图和收益指标，无净值时安全降级。

### 投递

- Markdown 和 PNG 使用同一报告日期、主题版本和内容 hash。
- bot 只发送到显式个人目标或既有明确受众目标。
- 图片上传失败不自动发送到其他目标。
- 相同报告、主题和内容不会重复发送。

## 9. 发布顺序

1. `quant-platform` 或策略 owner：确认通用表现序列机制和 artifact 生产能力。
2. 策略/回测 owner：发布 `weekly_basket.performance.v1` 及 receipt。
3. `quant-intel-platform`：实现内容模型、主题 registry、Markdown/PNG renderer 和周报适配器。
4. `quant-intel-platform`：接入晨报、晚报适配器，默认保持 `warm_light`。
5. `quant-intel-platform`：接入 `dark_terminal` 主题并完成视觉回归。
6. `quant-intel-deploy`：增加主题和 performance artifact 的显式环境变量，默认不改变现有调度行为。
7. 离线 smoke、生产 shadow、人工视觉检查后再切换周报主题。

跨仓修改必须先合并 provider，再合并 consumer，最后更新 deploy。任一 provider 尚未发布时，consumer 只保留可选输入和明确的无图降级，不引用开发 worktree 路径。

## 10. 风险与控制

| 风险 | 控制 |
| --- | --- |
| 主题迁移改变报告内容 | 内容模型测试和旧关键段落回归 |
| PNG 与 Markdown 内容不一致 | 两者都从同一个 `ReportDocument` 渲染，并记录同一内容 hash |
| 净值 artifact 误用或过期 | schema、日期、hash、来源和 receipt fail closed |
| Feishu 图片上传失败 | 保留本地产物，receipt 标记失败，不切换受众 |
| 深色主题被误删 | 主题注册表和旧渲染快照保留 |
| 一次迁移范围过大 | 周报先行，晨报/晚报分阶段迁移，默认主题不变 |

## 11. 验收标准

- 可以用同一份周报内容分别生成 `warm_light`、`research_editorial` 和 `dark_terminal` 输出。
- 周报在有合法 performance artifact 时显示净值图，没有时显示明确降级说明。
- 晨报和晚报完成公共内容模型适配，默认输出不改变业务内容。
- 深色主题仍可显式选择，且不依赖旧模块的隐式全局状态。
- 所有报告投递继续使用现有受众隔离、幂等和 receipt 机制。
- 生产路径只引用合并后的固定 release，不引用任务 worktree。

