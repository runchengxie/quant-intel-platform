# Astro Daily Chart Consumer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在公开日报站按报告身份安全导入经过独立审核的六图数据，并以 Astro 静态页和按需互动图呈现。

**Architecture:** 保留现有 Python 报告生产、五交易日窗口及 Markdown URL；新增严格的 public 图表清单验证、预览/应用/归档及构建期显式复制。Astro 从已审核公开快照生成首页与逐期页，正文和数值表先静态可读，图形组件仅在用户展开后按期加载 JSON 与 ECharts。旧页面构建仅在对照测试通过后退役，生产切换留给部署仓库。

**Tech Stack:** Python 3、pytest、Astro、React、ECharts、Node 测试、Ruff、ty。

**Spec:** `docs/superpowers/specs/2026-09-24-astro-daily-charts-design.md`。

## Global Constraints

- 遵守本仓 `AGENTS.md`：独立 worktree、PR 审核、公开窗口最多五个日期、只导入 `publication: public`、私有归档在仓库外。
- 上游已合并的 schema 固定为 `market_intel.a_share_charts.v1`；六键顺序为 `dashboard,moneyflow,topic,sentiment,us_overnight,weekly_chart`；ID 必须为 `<date>-<morning|evening>`。
- `content_sha256` 按去掉该字段后的 JSON 对象以 `sort_keys=True,separators=(",", ":"),ensure_ascii=False` 序列化重算。`candidate` 不可因字段改名或改状态被视为 public。
- 导入输入只能是审核后、显式 `publication: public` 的新清单；来源 URL、逐点 ISO 观测日、有限数值、状态、路径均重新校验。普通 `missing/skipped` 不得带点。
- 不发布私有 PNG、原始明细、聊天 ID 或凭据；数据文件按 `data/charts/<report_id>.json` 一期一份。既有美股日报文本/Markdown下载链接不变。
- Astro `site` 与 `base` 必须保持 GitHub Pages `/market-intel-pages/` 子路径；互动代码不进入首页初始资源，不用颜色作为唯一涨跌指示。
- 构建输出在仓库外专用临时目录验证；不向生产发布、不更改定时器。当前无已审核 public 六图时必须显示缺项，不用测试值填充。

## Review Focus

- 有人把 `publication: candidate` 的原始 provider JSON传给导入器：必须拒绝，不能自动改成 public；Task 1 负例。
- 已公开图表文件与报告索引不同日、同名晨晚报路径互换：必须拒绝或缺项，不能串期；Task 1/2 负例。
- SHA 正确但点内 URL 指向内网、值为 `NaN`、日期非法或附带私有字段：必须拒绝；Task 1 负例。
- 浏览器禁用 JavaScript或未展开图表：报告正文和数值表仍可读，首页不请求六张 PNG/ECharts；Task 3/4 构建与浏览器检查。
- 图表数据缺失、降级或部分美股点集：页面应保留六卡与真实日期/限制，切换日期后不显示上期点；Task 3/4 测试。

---

### Task 1: 公开六图契约验证及预览导入

**Files:**
- Create: `scripts/chart_contract.py`（纯校验、哈希、身份和隐私边界）
- Create: `scripts/import_charts.py`（预览、原子应用、外部归档）
- Test: `tests/test_chart_contract.py`、`tests/test_import_charts.py`

**Interfaces:**
- Consumes: provider `market_intel.a_share_charts.v1` 字段；报告索引 `data/reports.json`。
- Produces: `validate_public_chart(payload: object, *, expected_id: str | None = None) -> dict`；`import_charts(root: Path, source: Path, archive: Path, *, apply: bool = False) -> dict`。

- [ ] **Step 1: 写失败测试。** 以固定六卡构造 `publication: public` 的小型合成清单和正确 SHA；断言 `candidate`、多余字段、错误 hash、非有限数、内网 URL、缺项带值、错误 `report_id` 拒绝。导入测试构造报告索引，预览不得写入，应用只写 `data/charts/<id>.json` 并归档先前版本；重复应用无变化。

```python
def test_candidate_cannot_be_imported(valid_public_chart):
    valid_public_chart["publication"] = "candidate"
    with pytest.raises(ValueError, match="public"):
        validate_public_chart(valid_public_chart)

def test_preview_does_not_write(site_root, public_chart_path, archive_root):
    result = import_charts(site_root, public_chart_path, archive_root)
    assert result == {"changed": 1, "report_id": "2026-09-18-morning", "applied": False}
    assert not (site_root / "data/charts/2026-09-18-morning.json").exists()
```
- [ ] **Step 2: 运行 `python3 -m pytest tests/test_chart_contract.py tests/test_import_charts.py -q`，确认缺接口失败。**
- [ ] **Step 3: 实现验证与导入。** 解析 `date.fromisoformat`、`datetime.fromisoformat`（生成时间须带时区）、`math.isfinite`；`urlsplit` 要求公开 HTTPS 主机；按六键与白名单重建对象并重算 SHA；校验 ID 日期/类型和报告索引存在。预览返回 `changed/report_id/applied`；应用先验证，外部归档旧版本，再同目录临时文件 `replace`；不得直接改写源输入。

```python
canonical = json.dumps({k: v for k, v in payload.items() if k != "content_sha256"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
if hashlib.sha256(canonical).hexdigest() != payload.get("content_sha256"):
    raise ValueError("chart content hash mismatch")
if payload.get("publication") != "public":
    raise ValueError("only reviewed public charts may be imported")
destination = root / "data" / "charts" / f"{report_id}.json"
with NamedTemporaryFile(dir=destination.parent, delete=False) as staged:
    staged.write(json.dumps(validated, ensure_ascii=False, indent=2).encode())
Path(staged.name).replace(destination)
```
- [ ] **Step 4: 运行新增测试、`ruff check scripts/chart_contract.py scripts/import_charts.py tests/test_chart_contract.py tests/test_import_charts.py`、`ty check`，确认通过。**
- [ ] **Step 5: 提交 `feat: validate and import reviewed public charts`。**

### Task 2: 公开构建白名单与产物审核

**Files:**
- Modify: `scripts/build_site.py`
- Create: `scripts/audit_chart_artifact.py`
- Test: `tests/test_build_site.py`、`tests/test_audit_chart_artifact.py`

**Interfaces:**
- Consumes: Task 1 的 `validate_public_chart`，`data/charts/<id>.json`。
- Produces: `copy_public_charts(root: Path, output: Path, report_ids: set[str]) -> list[str]`；`audit_chart_artifact(output: Path) -> dict`。

- [ ] **Step 1: 写失败测试。** 构建一个五日期窗口的合成站点，放入有效图表、窗口外图表、candidate、同名另一 kind 图表；仅当期且 public 图表能复制到站点。无图表时正常构建。审计扫描构建产物中的 `data/charts`，再次核对哈希/身份与私有路径、凭据样式文本。

```python
def test_build_copies_only_indexed_public_charts(site_root, tmp_path, valid_public_chart):
    chart = site_root / "data/charts/2026-09-18-morning.json"
    chart.parent.mkdir(parents=True)
    chart.write_text(json.dumps(valid_public_chart), encoding="utf-8")
    build_site(site_root, tmp_path / "site")
    assert (tmp_path / "site/data/charts/2026-09-18-morning.json").is_file()
    assert not (tmp_path / "site/data/charts/2026-09-11-morning.json").exists()
```
- [ ] **Step 2: 运行 `python3 -m pytest tests/test_build_site.py tests/test_audit_chart_artifact.py -q`，确认新增断言失败。**
- [ ] **Step 3: 在既有 `build_site` 的报告窗口校验后仅复制白名单图表，存在不合法当期图表则构建失败；窗口外文件不复制。审计函数返回文件数/报告 ID，发现不匹配以 `ValueError` 失败。**

```python
for report_id in report_ids:
    source = root / "data" / "charts" / f"{report_id}.json"
    if source.is_file():
        payload = validate_public_chart(json.loads(source.read_text(encoding="utf-8")), expected_id=report_id)
        write_json(output / "data" / "charts" / f"{report_id}.json", payload)
```
- [ ] **Step 4: 运行定向测试与 `python3 scripts/build_site.py --output /tmp/market-intel-chart-build-check`，对真实无图表快照检查原报告 URL 未变化。**
- [ ] **Step 5: 提交 `feat: include only reviewed chart data in public builds`。**

### Task 3: Astro 首页和逐期静态正文

**Files:**
- Create: `package.json`、`package-lock.json`、`astro.config.mjs`、`src/pages/index.astro`、`src/pages/reports/[id].astro`、`src/components/ChartCards.astro`、`src/lib/reports.mjs`、`src/lib/markdown.mjs`
- Modify: `scripts/build_site.py`、`README.md`
- Test: `tests/astro-pages.test.cjs`、`tests/test_build_site.py`

**Interfaces:**
- Consumes: Task 2 构建的公开报告/六图数据和原 `reports/*.md`；既有 `data/market_daily_report.json`、`data/insights.json`、`data/daily_summaries.json`。
- Produces: GitHub Pages base-aware Astro 静态首页与每个报告的 `/reports/<id>/` 页；正文 HTML、六卡状态与数值表在 HTML 初始产物中可读。

- [ ] **Step 1: 写失败测试。** `node --test tests/astro-pages.test.cjs` 断言 package 脚本、Astro base、构建出的 `index.html` 和报告页有报告正文、Markdown GFM 表格、六个状态卡、零 JS 时可见的数值表、原始 Markdown 链接；当图表缺项时不出现测试值。Python 构建测试断言 Astro 产物保留 `/market-intel-pages/` 子路径与美股下载文件。

```js
test('static report is readable without JavaScript', async () => {
  const html = await readFile('dist/reports/2026-09-18-morning/index.html', 'utf8');
  assert.match(html, /<table/);
  assert.match(html, /data-chart-key="dashboard"/);
  assert.match(html, /\/market-intel-pages\/reports\/2026-09-18-morning\.md/);
});
```
- [ ] **Step 2: 运行新增测试确认失败。**
- [ ] **Step 3: 添加锁定依赖并构建 Astro 页面。** 首页由构建期读取五交易日报告、简评、美股日报和解读生成静态 HTML；报告页按 ID `getStaticPaths` 单期生成。Markdown 以 GFM 渲染后严格消毒原始 HTML；链接加 base，外链保留 `rel=noopener`。`ChartCards.astro` 先静态六卡/表/来源，状态缺项不展示虚构值。旧静态文件保留作回退，`build_site.py` 的 Astro 调用先在暂存目录产出且全部验证成功后再替换目标。

```astro
---
import { loadReports } from '../../lib/reports.mjs';
export async function getStaticPaths() {
  return loadReports().map((report) => ({ params: { id: report.id }, props: { report } }));
}
const { report } = Astro.props;
---
<main><h1>{report.title}</h1><ChartCards reportId={report.id} /></main>
```

`astro.config.mjs` 使用 `defineConfig({site:'https://runchengxie.github.io',base:'/market-intel-pages',integrations:[react()]})`；`src/lib/markdown.mjs` 使用 GFM parser 后经 `sanitize-html` 允许表格、段落、标题、列表、链接，不允许 raw script/iframe。
- [ ] **Step 4: 运行 `npm ci`、`npm run build`、Node/Python 定向测试，并对比旧站首页、五日期窗口、Markdown 与下载链接。**
- [ ] **Step 5: 提交 `feat: render daily reports with Astro`。**

### Task 4: 按需交互图及完整门禁

**Files:**
- Create: `src/components/ChartIsland.jsx`、`src/lib/chart-data.mjs`
- Modify: `astro.config.mjs`、`src/components/ChartCards.astro`、`src/pages/reports/[id].astro`、`styles.css`、`docs/daily-generation-options.md`
- Test: `tests/chart-data.test.cjs`、`tests/astro-pages.test.cjs`

**Interfaces:**
- Consumes: `data/charts/<id>.json` 的已审核六卡；单期 URL 仅该报告。
- Produces: 用户展开后动态加载单期 JSON/ECharts 的客户端岛，悬停值、图例切换、数值表和来源；无图数据只展示缺项。

- [ ] **Step 1: 写失败测试。** 校验日期/类型切换后只请求当前 `report_id`，展开前首页/逐期页不含 ECharts 与六 PNG 请求；图表轴有单位、正负同时带符号及颜色，缺项/降级保留原因和原始观测日；静态表与动态数据逐点一致。

```js
test('chart loader requests only selected report', async () => {
  const urls = [];
  await loadChart('2026-09-18-morning', (url) => { urls.push(url); return fixtureResponse; });
  assert.deepEqual(urls, ['/market-intel-pages/data/charts/2026-09-18-morning.json']);
});
```
- [ ] **Step 2: 运行 `node --test tests/chart-data.test.cjs tests/astro-pages.test.cjs`，确认失败。**
- [ ] **Step 3: 实现 React/ECharts island（或同等按需 Astro 客户端组件）。** 仅交互时 `import('echarts')`，`fetch` 只指向当前期 JSON；图例、缩放与键盘焦点可用。静态表由 Astro 生成，不依赖 hydration；暖色变量复用现有 CSS，涨跌有 `+`/`−` 标签和零线。

```jsx
async function openChart(reportId, key) {
  const report = await loadChart(reportId, fetch);
  const card = report.charts.find((item) => item.key === key);
  if (!card || !['ok', 'degraded'].includes(card.status)) return;
  const echarts = await import('echarts');
  return echarts.init(container).setOption(toOption(card));
}
```
- [ ] **Step 4: 执行本仓 `AGENTS.md` 的完整 Python/Node/构建/结构/pip-audit 门禁、浏览器桌面/窄屏/无脚本与网络检查，记录真实产物大小和与旧版差异；`git diff --check`。**
- [ ] **Step 5: 更新 README 与运行记录，提交、推送、PR；独立整分支复核和远端检查通过后合并。没有真实逐点审核时不得把候选强行发布。**

## Handoff

本计划只负责 Pages consumer 与静态站；生产定时器和发布白名单在 `quant-intel-deploy` 单独计划/PR。导入器仍只接受明示 public 的经审清单，provider candidate 必须另有逐点核验与许可结论。
