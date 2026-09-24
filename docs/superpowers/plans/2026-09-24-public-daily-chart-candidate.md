# Public Daily Chart Candidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从既有 A 股晨晚报六图的已验证输入生成带来源、原始观测日和质量状态的版本化公开候选 JSON，供后续 Pages 审核导入，而不发布 PNG 或原始明细。

**Architecture:** 图表生产仍属于 `quant-intel-platform`。生成 PNG 时同步保存同口径的有限图表就绪数值到私有 manifest；新增离线导出命令将其整理为六卡候选，校验后原子写入仓库外目录。候选不是已批准公开产物，不发送飞书，也不修改现有图表文件名。晚报复用当日图表生成数据，但导出身份明确为 `evening`。

**Tech Stack:** Python 3、pandas、现有 `a-share-daily` CLI、pytest、Ruff、ty。

**Spec:** [Astro 日报与飞书图表整合设计](https://github.com/runchengxie/market-intel-pages/blob/feat/astro-chart-design-root/docs/superpowers/specs/2026-09-24-astro-daily-charts-design.md)。本计划只实现 provider；Pages 导入与 Astro、私有部署各自另立计划和 PR。

## Global Constraints

- 遵守本仓 `AGENTS.md`：从 `origin/main` 建独立 worktree、测试后 PR，不改共享 hooks，不直接写生产目录。
- 候选 schema 固定为 `market_intel.a_share_charts.v1`；`publication` 固定为 `candidate`，由后续审核流程决定是否公开。
- 目标日期为 `YYYY-MM-DD`；每个候选恰有按 `dashboard, moneyflow, topic, sentiment, us_overnight, weekly_chart` 顺序排列的六卡；`report_id` 为 `<date>-<kind>`。
- 卡片状态只用 `ok`、`degraded`、`missing`、`skipped`；只有前两者允许 `points`，每点带 `label`、有限数值 `value`、`unit`、`observation_date`、`source_label`、`source_url`。来源链接必须来自已知来源配置，不凭空生成数据页链接。
- 顶层 `content_sha256` 为其他顶层字段按 `sort_keys=True`、`separators=(",", ":")`、`ensure_ascii=False` 序列化后的 SHA-256；consumer 逐字节重算。
- 替代数据保留其真实观测日；占位 PNG 及 `charts.paths` 不决定质量状态，私有路径不得进入候选。缺来源、缺日期、非有限数值不能降级为 `ok`。
- 新闻解释、模型判断、飞书目标、凭据和全量股票明细均不进入候选。现有 PNG/飞书投递行为保持不变。

## Review Focus

- 占位 PNG 文件存在但源图表报错：候选仍为 `missing`，不能显示伪造数值；Task 1/3 测。
- `moneyflow_ths` 回退到较早分区：候选为 `degraded` 且每点用实际分区日期；Task 2 测。
- 美股隔夜快照目标日期与行情原始日期不同：保留美东行情观测日，缺明细日期时不声称当日；Task 2 测。
- 晨晚报使用相同 `daily_*.png` 文件名：候选身份和输出文件仍互不覆盖；Task 3 测。
- 源 manifest 含私有路径或无限值：导出拒绝或剔除危险字段，绝不把原对象直接序列化；Task 1/3 测。

---

### Task 1: 候选 schema、状态和安全写入

**Files:**
- Create: `src/a_share_daily/charts/public_contract.py`
- Test: `tests/a_share_daily/test_public_chart_contract.py`
- Modify: `docs/data-ownership.md`

**Interfaces:**
- Consumes: 完整 `date: str`、`kind: str`、六个由 Task 2 提供的卡片 `Mapping[str, object]`。
- Produces: `build_candidate(date: str, kind: str, cards: Mapping[str, Mapping[str, object]], generated_at: str) -> dict[str, object]`；`write_candidate(path: Path, payload: Mapping[str, object]) -> None`。Task 3 调用这两个函数。

- [ ] **Step 1: 写失败测试。** 测试六卡固定顺序、`report_id`、禁止额外源字段，并用 `math.inf`、空 `source_url`、坏日期、带绝对私有路径的点及占位图状态做拒绝样例：

```python
def test_candidate_rejects_unverified_points():
    cards = {key: {"key": key, "title": key, "status": "missing", "reason": "无当日数据", "points": []} for key in CHART_KEYS}
    cards["moneyflow"] = {"key": "moneyflow", "title": "资金流向", "status": "ok", "points": [{"label": "样例", "value": float("inf"), "unit": "亿元", "observation_date": "2026-09-18", "source_label": "测试数据", "source_url": "https://example.test/source"}]}
    with pytest.raises(ValueError, match="finite"):
        build_candidate("2026-09-18", "morning", cards, "2026-09-19T07:00:00+08:00")
```

- [ ] **Step 2: 运行 `uv run pytest tests/a_share_daily/test_public_chart_contract.py -q`，确认测试先因缺失接口失败。**
- [ ] **Step 3: 实现明确字段白名单与校验。** 只从 `CHART_KEYS` 重建输出对象，不做 `dict(manifest)` 或从 PNG 路径猜状态。`missing/skipped` 必须 `points=[]` 且有 `reason`；`ok/degraded` 必须至少一点且每点日期为真实 ISO 日期，数值通过 `math.isfinite`。`write_candidate` 在目标目录同级临时文件写入并 `replace`；拒绝仓库内目标路径。核心形态：

```python
CHART_KEYS = ("dashboard", "moneyflow", "topic", "sentiment", "us_overnight", "weekly_chart")
SCHEMA = "market_intel.a_share_charts.v1"
payload = {"schema_version": SCHEMA, "publication": "candidate", "report_id": f"{date}-{kind}", "date": date, "kind": kind, "generated_at": generated_at, "charts": validated_cards}
canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
```

- [ ] **Step 4: 运行同一测试、`uv run ruff check src/a_share_daily/charts/public_contract.py tests/a_share_daily/test_public_chart_contract.py`，确认通过。**
- [ ] **Step 5: 文档写清候选不是公开批准及外部存储要求；提交本任务。**

### Task 2: 从六张图的同口径输入提取有限点集

**Files:**
- Create: `src/a_share_daily/charts/public_extract.py`
- Modify: `src/a_share_daily/charts/dashboard.py`、`sentiment.py`、`moneyflow.py`、`topic.py`、`weekly_chart.py`、`us_overnight.py`（仅提取已在绘图中使用的纯计算 helper；不改 PNG 展示口径）
- Test: `tests/a_share_daily/test_public_chart_extract.py`

**Interfaces:**
- Consumes: `inputs` 映射包含按图键命名的数据（如 `moneyflow: DataFrame`），另有 `<key>_observation_date: str`、`<key>_source_label: str`、`<key>_source_url: str`。多日期图的每行使用行内 `date`，而非统一日期。绘图当次使用的 `daily`、`topic_summary`、`week_daily`、`cross_market`、融资余额与成交额序列仍按原有类型传入。
- Produces: `extract_chart_points(key: str, inputs: Mapping[str, object], target_date: str) -> list[dict[str, object]]`。调用方按 key 存放于私有 manifest 的 `charts.public_points`，不把 DataFrame 或源路径直接放进去。

- [ ] **Step 1: 写失败测试。** 使用极小合成输入，断言情绪涨跌家数、资金流入/流出 Top-N、主题权重、周度广度/成交额、仪表盘及美股隔夜涨跌与既有绘图 helper 一致。另测滞后资金流和美股日期：

```python
def test_moneyflow_uses_actual_observation_date():
    inputs = {"moneyflow": pd.DataFrame([{"name": "样例公司", "ts_code": "000001.SZ", "net_amount": 11_000}]), "moneyflow_observation_date": "2026-09-17", "moneyflow_source_label": "测试数据", "moneyflow_source_url": "https://example.test/source"}
    points = extract_chart_points("moneyflow", inputs, "2026-09-18")
    assert points[0]["observation_date"] == "2026-09-17"
    assert points[0]["unit"] == "亿元"
```

- [ ] **Step 2: 运行 `uv run pytest tests/a_share_daily/test_public_chart_extract.py -q`，确认缺接口失败。**
- [ ] **Step 3: 实现各图的同口径提取。** `sentiment` 复用 `_sentiment_stats`；`weekly_chart` 复用 `_daily_stats`；`topic` 复用 `load_topic_summary` 的已校验权重和 `format_topic_label`；`moneyflow` 复用 `abs(net_amount)>1000`、流入前 8/流出前 5 与 `/1e4` 亿元换算；`us_overnight` 使用 `SYMBOLS`/`LABELS` 映射但从快照字段读取实际观测日；`dashboard` 输出广度、五日成交额、融资余额和情绪卡各自的单位和日期。只保留图所需有限点集，不暴露全市场日线。示例原则：

```python
df = moneyflow[moneyflow["net_amount"].abs() > 1_000]
selected = list(df.nlargest(8, "net_amount").itertuples()) + list(df.nsmallest(5, "net_amount").itertuples())
points = [{"label": row.name, "value": float(row.net_amount) / 1e4, "unit": "亿元", "observation_date": actual_date, "source_label": source_label, "source_url": source_url} for row in selected]
```

- [ ] **Step 4: 运行新测试及现有 `tests/test_chart_layout.py`、`tests/test_a_share_moneyflow_chart.py`、`tests/test_us_overnight_chart.py`，确认 PNG 输出未回归。**
- [ ] **Step 5: 提交本任务。**

### Task 3: 私有 manifest 与离线导出 CLI

**Files:**
- Modify: `src/a_share_daily/pipeline.py`、`src/a_share_daily/evening_manifest.py`、`src/a_share_daily/cli.py`
- Create: `src/a_share_daily/charts/public_export.py`
- Test: `tests/a_share_daily/test_public_chart_export.py`、`tests/test_a_share_daily_cli.py`

**Interfaces:**
- Consumes: Task 2 的 `charts.public_points` 与现有 `charts.ok/degraded/failed/skipped/errors`，Task 1 的 `build_candidate` 和 `write_candidate`。
- Produces: `a-share-daily chart-candidate --manifest PATH --out PATH --date YYYYMMDD --kind morning|evening`。无网络抓取、无飞书发送；成功时只打印输出路径。

- [ ] **Step 1: 写失败测试。** 构造含占位 PNG 路径、`errors["topic"]`、降级资金流、相同 `daily_dashboard.png` 路径的晨晚 manifest；分别导出不同文件，断言六卡质量状态、观测日和文件内容不串期。测试 `--out` 指向仓库、日期不符、JSON 非对象时非零退出且不覆盖已有文件：

```python
def test_evening_export_has_separate_identity(tmp_path, manifest_fixture):
    morning = export_candidate(manifest_fixture, date="20260918", kind="morning")
    evening_manifest = build_evening_manifest(manifest_fixture, expected_date="20260918")
    evening = export_candidate(evening_manifest, date="20260918", kind="evening")
    assert morning["report_id"] == "2026-09-18-morning"
    assert evening["report_id"] == "2026-09-18-evening"
    assert len(evening["charts"]) == 6
```

在该测试文件定义 `manifest_fixture` 为 `date="20260918"`、`report_kind="morning"`、固定 `generated_at`、六图 `charts.ok/degraded/failed/skipped` 与 `charts.public_points` 的小型合成 manifest；包含相同的 PNG 路径但不把路径写入点。使用 `tmp_path` 写两个不同候选文件，断言两文件均存在且 hash 各自可重算。

- [ ] **Step 2: 运行 `uv run pytest tests/a_share_daily/test_public_chart_export.py tests/test_a_share_daily_cli.py -q`，确认新测试失败。**
- [ ] **Step 3: 在 `step_charts` 生成每图时记录 Task 2 的有限点集与实际来源日期；`run_morning` 在跨市场快照取得后记录美股点集和 `generated_at`。** 导出器只在 manifest 日期、`report_kind` 与请求完全匹配时组装卡片；`errors` 或占位导致 `missing`，`skipped` 优先为 `skipped`，实际替代日期或 `degraded` 为 `degraded`。晚报用 `build_evening_manifest` 的 `report_kind` 建立独立 ID。CLI 仅负责读取、调用和输出，不把环境中的密钥/路径写入候选。接口：

```python
def export_candidate(manifest: Mapping[str, object], *, date: str, kind: str) -> dict[str, object]:
    """Validate one private report manifest and return a six-card public candidate."""
```

- [ ] **Step 4: 运行新测试、`uv run pytest tests/daily_report tests/test_a_share_pipeline.py tests/test_a_share_report_delivery.py -q`，确认晨晚报和图表投递不回归。**
- [ ] **Step 5: 更新 CLI 帮助快照，提交本任务。**

### Task 4: 契约、隐私与完整质量门禁

**Files:**
- Modify: `docs/data-ownership.md`、`docs/data-fetch-architecture.md`
- Test: `tests/a_share_daily/test_public_chart_export.py`

**Interfaces:**
- Consumes: 前三任务的 CLI 与 schema。
- Produces: 不含真实用户数据的合成候选示例、运行方式和 consumer 可引用的固定契约测试。

- [ ] **Step 1: 加入端到端合成测试。** 通过 CLI 读取合成晨/晚 manifest，解析候选，只允许 schema 白名单字段，拒绝 `feishu_chat_id`、`/home/`、凭据样式文本及无限值；校验同输入重跑结果稳定（生成时间来自固定的 `manifest["generated_at"]`）：

```python
assert set(candidate) == {"schema_version", "publication", "report_id", "date", "kind", "generated_at", "charts", "content_sha256"}
assert "feishu_chat_id" not in json.dumps(candidate)
assert "/home/" not in json.dumps(candidate)
assert first_output.read_bytes() == second_output.read_bytes()
```
- [ ] **Step 2: 运行新测试，确认若安全扫描或稳定性尚未实现则失败。**
- [ ] **Step 3: 在文档写明源数据口径、观测日优先级、降级判定、候选到 `publication: public` 的人工/自动审核边界、回填与缺项样例；补齐使测试通过的最小校验。**
- [ ] **Step 4: 运行 `uv run pytest tests/a_share_daily/test_public_chart_contract.py tests/a_share_daily/test_public_chart_extract.py tests/a_share_daily/test_public_chart_export.py -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run ty check`、`uv run python project_tools/update_cli_help.py --check`、`uv run python project_tools/check_all.py --scope all`、`git diff --check`，记录真实结果。**
- [ ] **Step 5: 提交、推送并建本仓 PR。必需检查与评审通过才可合并；没有完整门禁时保持 Draft。合并后 consumer 才引用此 schema，生产部署另行授权。**

## Handoff

本计划产出可测试的 provider 候选 CLI，不把候选直接发布到公网。后续分别在 `market-intel-pages` 实施审核导入、Astro/交互图表，在 `quant-intel-deploy` 实施受限发布与回执；两者使用各自独立计划、worktree 和 PR。不要把 provider 工作树路径写入生产任务。
