# Report Content and Switchable Themes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax with - [ ] for tracking.

**Goal:** 将晨报、晚报、周报统一迁移到可切换主题的报告内容模型，并为周报接入可靠的历史净值 artifact 与 Feishu Markdown/PNG 双渲染。

**Architecture:** 策略/回测 owner 生成带版本、日期和 hash 的表现序列 artifact；quant-intel-platform 将现有报告适配成不可变 ReportDocument，再由主题 registry 交给 Markdown 或 PNG renderer；quant-intel-deploy 只提供显式主题和 artifact 路径。发布顺序固定为 provider → consumer → deploy，默认主题和旧报告内容保持兼容。

**Tech Stack:** Python 3.12+, frozen dataclass, JSON artifacts with SHA-256 receipts, matplotlib/Agg PNG rendering, Feishu lark-cli, pytest, Ruff, ty.

**Spec:** docs/superpowers/specs/2026-09-11-report-theme-system-design.md

## Global Constraints

- 不在报告仓库重新实现行情抓取、因子计算、组合构造或回测。
- weekly_basket.performance.v1 由策略/回测 owner 生产，报告仓只消费并校验。
- 默认主题保持当前生产行为；主题切换必须显式或通过 REPORT_THEME。
- 净值缺失、过期、hash 不匹配或少于两个点时安全降级，禁止绘制假数据。
- Markdown 和 PNG 必须从同一份 ReportDocument 渲染并记录同一内容 hash。
- Feishu 投递继续使用现有受众隔离、bot 身份和幂等 receipt。
- 每项仓库改动使用独立 worktree 和 feat/* 分支；provider 合并后才能推进 consumer。
- 所有新行为先写失败测试，再写最小实现；每个任务独立提交。

## File Map

Provider:
- quant-research/src/strategy_app/weekly_performance_artifact.py
- quant-research/src/strategy_app/weekly_backtest_bridge.py
- quant-research/tests/strategy_app/test_weekly_performance_artifact.py
- strategy-pipeline/src/strategy_pipeline/pipeline/output_artifacts.py
- strategy-pipeline/tests/test_pipeline_output_artifacts.py
- strategy-pipeline/docs/output-artifacts.md

Consumer:
- quant-intel-platform/src/a_share_daily/reporting/model.py
- quant-intel-platform/src/a_share_daily/reporting/performance.py
- quant-intel-platform/src/a_share_daily/reporting/themes.py
- quant-intel-platform/src/a_share_daily/reporting/render_markdown.py
- quant-intel-platform/src/a_share_daily/reporting/render_png.py
- quant-intel-platform/src/a_share_daily/reporting/artifacts.py
- quant-intel-platform/src/a_share_daily/reporting/adapters.py
- quant-intel-platform/src/a_share_daily/weekly_client_basket_render.py
- quant-intel-platform/src/a_share_daily/weekly_client_basket_delivery.py
- quant-intel-platform/src/a_share_daily/cli.py
- quant-intel-platform/tests/reporting/
- quant-intel-platform/tests/test_weekly_client_basket_render.py

Deploy:
- quant-intel-deploy/scripts/weekly_client_basket.sh
- quant-intel-deploy/scripts/systemd/weekly-client-basket.service
- quant-intel-deploy/tests/test_weekly_client_basket_script.py

---

### Task 1: Produce the weekly performance artifact

**Files:**
- Create: quant-research/src/strategy_app/weekly_performance_artifact.py
- Modify: quant-research/src/strategy_app/weekly_backtest_bridge.py
- Test: quant-research/tests/strategy_app/test_weekly_performance_artifact.py

**Interfaces:**
- write_weekly_performance_artifact(result, output_path, *, report_date, source, benchmark=None) -> PerformanceArtifact
- load_weekly_performance_artifact(path) -> PerformanceArtifact
- PerformanceArtifact contains schema_version, report_date, series, optional benchmark, source, artifact_sha256.

- [ ] **Step 1: Write the failing producer contract test.**

Use a synthetic PositionBacktestResult. Assert schema_version is weekly_basket.performance.v1, the first normalized NAV is 1.0, dates are ascending, and the file digest matches the recorded digest.

~~~python
def test_write_weekly_performance_artifact(tmp_path):
    artifact = write_weekly_performance_artifact(
        _synthetic_result(),
        tmp_path / "basket_performance.json",
        report_date="20260914",
        source="portfolio-backtester",
    )
    assert artifact.schema_version == "weekly_basket.performance.v1"
    assert artifact.series[0].nav == pytest.approx(1.0)
    assert artifact.series[0].date == "20260901"
~~~

- [ ] **Step 2: Run the test and verify it fails.**

Run: cd /home/richard/code/.worktrees/quant-research-weekly-performance && uv run pytest tests/strategy_app/test_weekly_performance_artifact.py -q

Expected: FAIL because the artifact module and writer do not exist.

- [ ] **Step 3: Implement frozen point/artifact types and fail-closed validation.**

Validate YYYYMMDD dates, ascending unique dates, finite positive NAVs, at least two points, last date not after report_date, optional benchmark alignment, and lowercase SHA-256. Serialize canonical JSON with sorted keys and write atomically through a temporary sibling file and Path.replace().

- [ ] **Step 4: Add loader tests for wrong schema, invalid digest, duplicate dates, future dates, and one-point series.**

Each invalid case must raise a named PerformanceArtifactError.

- [ ] **Step 5: Run checks and commit.**

~~~bash
uv run pytest tests/strategy_app/test_weekly_performance_artifact.py -q
uv run ruff check src/strategy_app/weekly_performance_artifact.py tests/strategy_app/test_weekly_performance_artifact.py
git add src/strategy_app/weekly_performance_artifact.py src/strategy_app/weekly_backtest_bridge.py tests/strategy_app/test_weekly_performance_artifact.py
git commit -m "feat: publish weekly basket performance artifact"
~~~

### Task 2: Register the provider output in strategy-pipeline

**Files:**
- Modify: strategy-pipeline/src/strategy_pipeline/pipeline/output_artifacts.py
- Modify: strategy-pipeline/tests/test_pipeline_output_artifacts.py
- Modify: strategy-pipeline/docs/output-artifacts.md

- [ ] **Step 1: Add a failing compatibility test.**

A context containing weekly_basket_performance_path must return that path in artifacts when enabled. An old context without that key must keep working and return the previous mapping.

- [ ] **Step 2: Run the focused test and verify failure.**

Run: cd /home/richard/code/.worktrees/strategy-pipeline-weekly-performance && uv run pytest tests/test_pipeline_output_artifacts.py -q

- [ ] **Step 3: Add optional registration only.**

Add the path to _initial_artifacts() and document that strategy-pipeline publishes the file/receipt but does not calculate NAV or import strategy code.

- [ ] **Step 4: Run the public checks and commit.**

~~~bash
uv run pytest tests/test_pipeline_output_artifacts.py -q
uv run ruff check src/strategy_pipeline/pipeline/output_artifacts.py tests/test_pipeline_output_artifacts.py
git add src/strategy_pipeline/pipeline/output_artifacts.py tests/test_pipeline_output_artifacts.py docs/output-artifacts.md
git commit -m "feat: register weekly performance artifact"
~~~

Merge Tasks 1 and 2 before consumer work depends on the published contract.

### Task 3: Add the common ReportDocument model

**Files:**
- Create: quant-intel-platform/src/a_share_daily/reporting/__init__.py
- Create: quant-intel-platform/src/a_share_daily/reporting/model.py
- Test: quant-intel-platform/tests/reporting/test_model.py

**Interfaces:**
- ReportDocument, ReportSection, MetricGroup, Metric, PositionCard, SeriesChart, Notice
- ReportDocument.content_hash() -> str

- [ ] **Step 1: Write failing construction/hash tests.**

Construct a document containing title, metrics, ordered sections, position cards, chart, and notices. Assert equal documents have equal hashes and changing a theme does not change content_hash.

- [ ] **Step 2: Run the focused test and verify failure.**

Run: cd /home/richard/code/.worktrees/quant-intel-platform-report-themes && uv run pytest tests/reporting/test_model.py -q

- [ ] **Step 3: Implement frozen dataclasses.**

Use tuples for ordered collections and copied mappings for metadata. Validate non-empty report type/date/title, finite numeric metrics, and position status values 新增/保留/剔除. Keep color, font, pixel position, and Markdown syntax out of the model.

- [ ] **Step 4: Run Ruff/tests and commit.**

~~~bash
uv run pytest tests/reporting/test_model.py -q
uv run ruff check src/a_share_daily/reporting/model.py tests/reporting/test_model.py
git add src/a_share_daily/reporting tests/reporting/test_model.py
git commit -m "feat: add report content model"
~~~

### Task 4: Add performance loading and display metrics

**Files:**
- Create: quant-intel-platform/src/a_share_daily/reporting/performance.py
- Test: quant-intel-platform/tests/reporting/test_performance.py

**Interfaces:**
- load_performance(path: Path, *, report_date: str) -> PerformanceSeries
- performance_metrics(series: PerformanceSeries, *, report_date: str) -> tuple[Metric, ...]
- PerformanceSeries.to_chart() -> SeriesChart

- [ ] **Step 1: Write failing valid/invalid artifact tests.**

Cover portfolio-only, portfolio-plus-benchmark, wrong schema, bad hash, unordered dates, future last date, and fewer than two points. Invalid input must raise PerformanceArtifactError and never produce a chart.

- [ ] **Step 2: Run the focused test and verify failure.**

Run: cd /home/richard/code/.worktrees/quant-intel-platform-report-themes && uv run pytest tests/reporting/test_performance.py -q

- [ ] **Step 3: Implement the loader and metrics.**

Normalize to 1.0 at the first point. Calculate recent 5-session, recent 21-session, YTD, and since-start returns when enough points exist. Missing windows produce status 不可用, never a fabricated percentage.

- [ ] **Step 4: Run tests and commit.**

~~~bash
uv run pytest tests/reporting/test_performance.py -q
uv run ruff check src/a_share_daily/reporting/performance.py tests/reporting/test_performance.py
git add src/a_share_daily/reporting/performance.py tests/reporting/test_performance.py
git commit -m "feat: consume weekly performance artifacts"
~~~

### Task 5: Add theme registry and three themes

**Files:**
- Create: quant-intel-platform/src/a_share_daily/reporting/themes.py
- Test: quant-intel-platform/tests/reporting/test_themes.py

**Interfaces:**
- get_theme(name: str) -> ReportTheme
- available_themes() -> tuple[str, ...]
- ReportTheme.tokens, layout, renderer_capabilities

- [ ] **Step 1: Write failing registry tests.**

Assert dark_terminal, warm_light, and research_editorial resolve; invalid names raise UnknownThemeError listing valid names; all required semantic tokens exist; changing themes does not alter a document content hash.

- [ ] **Step 2: Run the focused test and verify failure.**

Run: cd /home/richard/code/.worktrees/quant-intel-platform-report-themes && uv run pytest tests/reporting/test_themes.py -q

- [ ] **Step 3: Implement semantic tokens.**

Map warm_light from current chart values, dark_terminal from the existing dark client palette, and research_editorial to warm paper, serif title, thin rules, muted sleeve colors, and compact cards. Keep raw colors inside theme definitions only.

- [ ] **Step 4: Run tests and commit.**

~~~bash
uv run pytest tests/reporting/test_themes.py -q
uv run ruff check src/a_share_daily/reporting/themes.py tests/reporting/test_themes.py
git add src/a_share_daily/reporting/themes.py tests/reporting/test_themes.py
git commit -m "feat: add switchable report themes"
~~~

### Task 6: Implement Markdown and PNG renderers

**Files:**
- Create: quant-intel-platform/src/a_share_daily/reporting/render_markdown.py
- Create: quant-intel-platform/src/a_share_daily/reporting/render_png.py
- Test: quant-intel-platform/tests/reporting/test_renderers.py

**Interfaces:**
- render_markdown(document: ReportDocument, theme: ReportTheme) -> str
- render_png(document: ReportDocument, theme: ReportTheme, output_path: Path) -> Path

- [ ] **Step 1: Write failing renderer tests.**

Use one fixture document with metrics, position cards, portfolio series, benchmark series, and notices. Assert Markdown preserves values and order for all themes. Assert PNG dimensions, non-empty bytes, title presence, and theme-specific background.

- [ ] **Step 2: Run the focused test and verify failure.**

Run: cd /home/richard/code/.worktrees/quant-intel-platform-report-themes && uv run pytest tests/reporting/test_renderers.py -q

- [ ] **Step 3: Implement Markdown renderer.**

Render Chinese labels, compact cards, status tags, four performance metrics, and an explicit unavailable-data notice. Never put local file paths into Markdown image syntax.

- [ ] **Step 4: Implement PNG renderer.**

Use matplotlib Agg, fixed theme dimensions, CJK-safe font selection, two-column cards, low-saturation sleeve colors, a compact line chart, optional benchmark, and a small metric grid. No area fill by default. Write atomically and close figures.

- [ ] **Step 5: Run tests and commit.**

~~~bash
uv run pytest tests/reporting/test_renderers.py -q
uv run ruff check src/a_share_daily/reporting/render_markdown.py src/a_share_daily/reporting/render_png.py tests/reporting/test_renderers.py
git add src/a_share_daily/reporting/render_markdown.py src/a_share_daily/reporting/render_png.py tests/reporting/test_renderers.py
git commit -m "feat: render themed report markdown and png"
~~~

### Task 7: Migrate weekly basket and delivery

**Files:**
- Modify: quant-intel-platform/src/a_share_daily/weekly_client_basket_render.py
- Modify: quant-intel-platform/src/a_share_daily/weekly_client_basket_delivery.py
- Modify: quant-intel-platform/src/a_share_daily/cli.py
- Create: quant-intel-platform/tests/reporting/test_weekly_basket_adapter.py
- Create: quant-intel-platform/tests/test_weekly_client_basket_image_delivery.py

**Interfaces:**
- weekly_basket_document(artifact: BasketArtifact, performance: PerformanceSeries | None) -> ReportDocument
- write_rendered_outputs(..., *, theme_name: str, performance_path: Path | None = None) -> dict[str, Path]
- send_personal_basket_report(..., image_path: Path | None = None) -> DeliveryReceipt

- [ ] **Step 1: Write failing adapter and CLI tests.**

Assert ten cards, Chinese strategy/status labels, diff metrics, chart only with valid performance, CLI help for --theme/--performance, and image send only when an image exists. Include image hash in idempotency scope.

- [ ] **Step 2: Run focused tests and verify failure.**

Run: cd /home/richard/code/.worktrees/quant-intel-platform-report-themes && uv run pytest tests/reporting/test_weekly_basket_adapter.py tests/test_weekly_client_basket_image_delivery.py tests/test_weekly_client_basket_render.py -q

- [ ] **Step 3: Implement adapter and theme plumbing.**

Keep basket.json, basket.csv, and trade delta unchanged. Default to current compatible theme unless --theme or REPORT_THEME is set. Invalid/missing performance writes an unavailable-data notice and no report.png.

- [ ] **Step 4: Implement safe image delivery.**

Keep Markdown delivery primary. If report.png exists, upload with lark-cli im images create --as bot and send to the same explicit personal target. Record image hash, image key, theme version, and status; never log tokens.

- [ ] **Step 5: Run weekly regressions and commit.**

~~~bash
uv run pytest tests/test_weekly_client_basket*.py tests/test_a_share_daily_cli.py tests/reporting -q
uv run ruff check src/a_share_daily/weekly_client_basket_render.py src/a_share_daily/weekly_client_basket_delivery.py src/a_share_daily/reporting tests
git add src/a_share_daily/weekly_client_basket_render.py src/a_share_daily/weekly_client_basket_delivery.py src/a_share_daily/cli.py tests/reporting tests/test_weekly_client_basket_render.py tests/test_weekly_client_basket_image_delivery.py
git commit -m "feat: migrate weekly basket to themed reports"
~~~

### Task 8: Migrate morning and evening reports

**Files:**
- Create: quant-intel-platform/src/a_share_daily/reporting/adapters.py
- Modify: quant-intel-platform/src/a_share_daily/morning_report.py
- Modify: quant-intel-platform/src/a_share_daily/delivery/_render.py
- Modify: quant-intel-platform/src/a_share_daily/delivery/report_delivery.py
- Modify: quant-intel-platform/src/a_share_daily/cli.py
- Test: quant-intel-platform/tests/reporting/test_daily_report_adapters.py and existing morning/evening tests

- [ ] **Step 1: Capture current semantic content contracts.**

Assert existing headings, market-temperature labels, DailyWatch20 references, risk notices, and degraded-data wording. Compare semantic content, not whitespace or colors.

- [ ] **Step 2: Run the baseline tests.**

Run: cd /home/richard/code/.worktrees/quant-intel-platform-report-themes && uv run pytest tests/reporting/test_daily_report_adapters.py tests/test_morning_report.py tests/test_evening_review_pipeline_script.py -q

- [ ] **Step 3: Implement adapters without changing data assembly.**

Leave fetchers, freshness checks, artifact validation, and delivery state untouched. Keep warm_light as default and allow explicit --theme.

- [ ] **Step 4: Add dual-theme semantic regression tests.**

Render the same document under warm_light and dark_terminal; assert identical content hashes and different theme metadata/backgrounds.

- [ ] **Step 5: Run report regressions and commit.**

Use the existing evening pipeline regression test; do not skip the evening suite. Then run Ruff and commit:
~~~bash
uv run pytest tests/reporting/test_daily_report_adapters.py tests/test_morning_report.py tests/test_evening_review_pipeline_script.py -q
uv run ruff check src/a_share_daily/reporting/adapters.py src/a_share_daily/morning_report.py tests/reporting/test_daily_report_adapters.py
git add src/a_share_daily/reporting/adapters.py src/a_share_daily/morning_report.py src/a_share_daily/cli.py tests/reporting/test_daily_report_adapters.py tests/test_morning_report.py
git commit -m "feat: route daily reports through documents"
~~~

### Task 9: Preserve and verify dark terminal theme

**Files:**
- Modify: quant-intel-platform/src/a_share_daily/reporting/themes.py
- Modify: existing dark client renderer only where it delegates to theme tokens
- Create: quant-intel-platform/tests/reporting/test_dark_theme_compatibility.py

- [ ] **Step 1: Write failing compatibility tests.**

Assert dark background, light foreground, existing major headings, chart labels, and no warm-light token leakage. Assert dark output requires explicit selection when warm_light is default.

- [ ] **Step 2: Implement token delegation without deleting the old renderer.**

Map existing dark palette constants into semantic tokens. Keep the old path until the new renderer matches semantic sections.

- [ ] **Step 3: Run regressions and commit.**

~~~bash
uv run pytest tests/reporting/test_dark_theme_compatibility.py tests/test_chart_theme.py tests/test_chart_layout.py -q
uv run ruff check src/a_share_daily/reporting/themes.py tests/reporting/test_dark_theme_compatibility.py
git add src/a_share_daily/reporting/themes.py tests/reporting/test_dark_theme_compatibility.py
git commit -m "feat: preserve switchable dark report theme"
~~~

### Task 10: Add deployment switches and production-safe defaults

**Files:**
- Modify: quant-intel-deploy/scripts/weekly_client_basket.sh
- Modify: quant-intel-deploy/scripts/morning_pipeline.sh
- Modify: quant-intel-deploy/scripts/evening_pipeline.sh
- Modify: quant-intel-deploy/scripts/systemd/weekly-client-basket.service
- Modify: quant-intel-deploy/tests/test_weekly_client_basket_script.py

- [ ] **Step 1: Write failing script contract tests.**

Assert REPORT_THEME is passed only when configured, WEEKLY_BASKET_PERFORMANCE_ARTIFACT is passed only when the explicit file exists, dry-run remains the default, and the personal-send confirmation guard is unchanged.

- [ ] **Step 2: Run focused tests and verify failure.**

~~~bash
    cd /home/richard/code/.worktrees/quant-intel-deploy-report-themes
uv run pytest tests/test_weekly_client_basket_script.py -q
bash -n scripts/weekly_client_basket.sh
~~~

- [ ] **Step 3: Implement explicit environment plumbing.**

Do not infer a performance path from arbitrary output directories. A missing optional performance artifact yields a no-chart report, not a failed basket build.

- [ ] **Step 4: Run smoke tests and commit.**

~~~bash
uv run pytest tests/test_weekly_client_basket_script.py -q
bash -n scripts/weekly_client_basket.sh
git add scripts/weekly_client_basket.sh scripts/systemd/weekly-client-basket.service tests/test_weekly_client_basket_script.py
git commit -m "feat: configure report theme and performance artifact"
~~~

### Task 11: End-to-end verification and rollout

**Files:**
- Create: quant-intel-platform/tests/reporting/fixtures/weekly_basket_performance.json
- Create: quant-intel-platform/tests/reporting/test_end_to_end_report_outputs.py
- Update: the approved design/spec only with verified implementation notes

- [ ] **Step 1: Add deterministic fixture and dry-run test.**

Assert weekly-basket with --dry-run --theme research_editorial --performance fixture writes report.md, report.png, canonical basket files, and a receipt whose content/theme/image hashes agree.

- [ ] **Step 2: Run consumer checks.**

~~~bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests
uv run ty check
~~~

If repository-wide format reports unrelated pre-existing files, record them and run changed-file format checks separately; do not reformat unrelated files.

- [ ] **Step 3: Run provider → pipeline → consumer → deploy checks.**

~~~bash
cd /home/richard/code/.worktrees/quant-research-weekly-performance && uv run pytest tests/strategy_app/test_weekly_performance_artifact.py -q
cd /home/richard/code/.worktrees/strategy-pipeline-weekly-performance && uv run pytest tests/test_pipeline_output_artifacts.py -q
cd /home/richard/code/.worktrees/quant-intel-platform-report-themes && uv run pytest -q
cd /home/richard/code/.worktrees/quant-intel-deploy-report-themes && uv run pytest tests/test_weekly_client_basket_script.py -q
~~~

- [ ] **Step 4: Perform dry-run delivery verification.**

Confirm receipt includes theme_name, theme_version, and image_sha256 when present, and that no live Feishu call occurs. Real app sends require human approval of recipient and content.

- [ ] **Step 5: Push and open PRs in provider → consumer → deploy order.**

Do not commit production data, credentials, or worktree paths. Promote production only after all PRs merge and the fixed release procedure succeeds.

## Execution Notes

- Stop after Tasks 1–2 if the provider cannot expose authoritative daily NAV without introducing private strategy logic into a public repository.
- The weekly theme system may ship before the performance provider is live; it must render the explicit no-chart notice in that state.
- Morning/evening migration begins only after weekly adapter and theme registry pass semantic and visual regressions.
