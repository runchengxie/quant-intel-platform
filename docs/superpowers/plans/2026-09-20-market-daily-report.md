# 市场日报证据链 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `quant-intel-platform` 中建立可重放、带来源和证据校验的美股市场日报基础链路，并为 Hermes、部署仓库和 Pages 提供稳定的版本化产物。

**Architecture:** 先把确定性市场事实和事件标准化为不可变 JSON，再把窄范围研究任务的结论绑定到事实或事件证据。校验器拒绝无来源数字、超出截止时间的来源和未经证据支持的因果结论，日报渲染器只消费通过校验的 `daily_report.json`。首期只在平台仓库实现并生成 shadow 产物，部署调度和页面消费在后续独立变更中接入。

**Tech Stack:** Python 3.11+, dataclasses/TypedDict, JSON Schema-like runtime validation, existing `requests`/`pandas`/`yfinance` fetchers, pytest, ruff, ty, existing CLI and artifact receipt helpers.

**Spec:** `docs/superpowers/specs/2026-09-20-market-daily-report-research-design.md`

## Global Constraints

- 确定性数据源产生的事实不能被研究模型覆盖。
- 每条公开结论必须引用事实或事件 ID，并保留来源、来源时间和报告截止时间。
- 来源时间晚于报告截止时间时，校验器必须拒绝该结论。
- 研究提供商失败时保留确定性事实，报告必须标记降级状态。
- 不在公开产物中保存 API key、认证文件或未清理的原始模型输出。
- 每个日期和报告窗口必须幂等，重复运行不得覆盖较新的有效产物。
- 首期不输出自动交易建议、目标价或买卖指令。
- 跨仓库只通过公开 CLI、版本化 JSON 产物或稳定 HTTP 接口通信。

## Review Focus

- 截止时间边界：晚于 `as_of` 的新闻和修订不能进入报告。测试放在 Task 3 的时间过滤测试中。
- 确定性事实冲突：模型提供的数字与市场事实冲突时必须保留事实并记录冲突。测试放在 Task 4 的冲突测试中。
- 部分数据源失败：单个源失败不能让已完成的事实消失。测试放在 Task 2 的降级合并测试中。
- 无证据因果解释：没有事件或来源的“因为”表述必须被拒绝。测试放在 Task 4 的证据覆盖测试中。
- 重复运行与旧产物：重跑失败任务不能覆盖上一次有效产物。测试放在 Task 5 的幂等测试中。

### Task 1: 建立日报事实、事件和报告协议

**Files:**
- Create: `src/daily_messenger/daily_report/__init__.py`
- Create: `src/daily_messenger/daily_report/models.py`
- Create: `src/daily_messenger/daily_report/serialization.py`
- Modify: `src/research_contracts/artifact_envelope.py`
- Test: `tests/daily_report/test_models.py`
- Test: `tests/daily_report/test_serialization.py`

**Interfaces:**
- Consumes: 现有 ETL 字典、`research_contracts` 的 artifact envelope。
- Produces: `MarketFact`, `MarketEvent`, `ResearchClaim`, `DailyReport` 数据类型，以及 `to_dict()`、`from_dict()` 和 `write_json()`。

- [ ] **Step 1: Write the failing tests**

```python
def test_fact_round_trip_preserves_provenance():
    fact = MarketFact(
        id="spx.close",
        metric="index_return",
        instrument="SPX",
        value=0.16,
        previous=0.0,
        change=0.16,
        unit="percent",
        source="fmp",
        source_url="https://example.test/spx",
        source_time=datetime(2026, 9, 18, 20, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 19, 1, tzinfo=UTC),
        quality="ok",
    )
    assert MarketFact.from_dict(fact.to_dict()) == fact


def test_report_requires_schema_version_and_as_of():
    with pytest.raises(ValueError, match="schema_version"):
        DailyReport.from_dict({"sections": []})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/daily_report/test_models.py tests/daily_report/test_serialization.py -q`
Expected: FAIL because the new types and serializers do not exist.

- [ ] **Step 3: Implement the minimal protocol types**

Use frozen dataclasses with explicit types. `ResearchClaim.confidence` accepts only `confirmed`, `likely`, `possible`, `unclear`. `DailyReport` stores `schema_version`, `as_of`, `generated_at`, `run_id`, `sections`, `missing_sources`, `quality_summary`, and `source_status`. Reject unknown required-field omissions and serialize datetimes as ISO 8601 UTC strings.

- [ ] **Step 4: Add artifact envelope metadata**

Extend the existing envelope helper so public report artifacts include schema version, run ID, cutoff, content hash, and generated timestamp without changing existing A-share consumers. Add backward-compatible defaults for older envelope readers.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/daily_report/test_models.py tests/daily_report/test_serialization.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/daily_messenger/daily_report src/research_contracts/artifact_envelope.py tests/daily_report
git commit -m "feat: add daily report artifact contracts"
```

### Task 2: Normalize market facts and cross-market fields

**Files:**
- Create: `src/daily_messenger/daily_report/facts.py`
- Modify: `src/daily_messenger/etl/fetchers/quotes.py`
- Modify: `src/daily_messenger/etl/fetchers/fred.py`
- Modify: `src/daily_messenger/etl/fetchers/fmp.py`
- Modify: `src/daily_messenger/etl/fetchers/normalize.py`
- Test: `tests/daily_report/test_facts.py`
- Test: `tests/daily_report/test_fact_degradation.py`

**Interfaces:**
- Consumes: existing fetcher payloads and `MarketFact` from Task 1.
- Produces: `build_market_facts(raw_payloads: Mapping[str, Any], *, as_of: datetime) -> list[MarketFact]` and `merge_fact_batches(batches: Iterable[Sequence[MarketFact]]) -> list[MarketFact]`.

- [ ] **Step 1: Write failing tests**

```python
def test_build_market_facts_includes_curve_and_cross_market_metrics(sample_payloads):
    facts = build_market_facts(sample_payloads, as_of=AS_OF)
    assert fact_by_id(facts, "treasury.2y.change_bp").value == 8.0
    assert fact_by_id(facts, "treasury.10y.change_bp").value == 4.0
    assert fact_by_id(facts, "cross_market.wti.change_percent").value == -1.6


def test_failed_source_is_marked_degraded_without_dropping_other_facts(sample_payloads):
    sample_payloads["fmp"] = FetchFailure("quota")
    facts = build_market_facts(sample_payloads, as_of=AS_OF)
    assert fact_by_id(facts, "treasury.10y.change_bp") .quality == "degraded"
    assert fact_by_id(facts, "index.spx.change_percent").quality == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/daily_report/test_facts.py tests/daily_report/test_fact_degradation.py -q`
Expected: FAIL because fact normalization is not implemented.

- [ ] **Step 3: Implement normalization**

Map existing index, sector, mover, FRED, Treasury, FX, commodity and crypto payloads into stable IDs. Add 2Y, 5Y, 10Y and 30Y curve fields when the source supplies them. Preserve source URL, source time and retrieval time. For a failed source, emit a source-status record and keep unrelated facts. Do not invent values for missing fields.

- [ ] **Step 4: Implement merge and deterministic calculations**

Deduplicate by fact ID, prefer the source configured as authoritative, and compute change basis points and percent changes from the source values. Add a helper `classify_curve_move(facts) -> str | None` that returns `bear_flattening`, `bear_steepening`, `bull_flattening`, `bull_steepening`, or `None` based on short-versus-long tenor changes.

- [ ] **Step 5: Run tests and static checks**

Run: `uv run pytest tests/daily_report/test_facts.py tests/daily_report/test_fact_degradation.py -q`
Expected: PASS.
Run: `uv run ruff check src/daily_messenger/daily_report src/daily_messenger/etl/fetchers`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/daily_messenger/daily_report/facts.py src/daily_messenger/etl/fetchers tests/daily_report
git commit -m "feat: normalize market facts and cross-market fields"
```

### Task 3: Normalize market events with point-in-time filtering

**Files:**
- Create: `src/daily_messenger/daily_report/events.py`
- Modify: `src/daily_messenger/etl/fetchers/events.py`
- Modify: `src/daily_messenger/etl/fetchers/edgar.py`
- Modify: `src/daily_messenger/common/news_contract.py`
- Test: `tests/daily_report/test_events.py`
- Test: `tests/daily_report/test_event_cutoff.py`

**Interfaces:**
- Consumes: economic calendar, SEC, Fed/news payloads and `MarketEvent`.
- Produces: `build_market_events(raw_events: Iterable[Mapping[str, Any]], *, as_of: datetime) -> list[MarketEvent]` and `filter_events_as_of(events, as_of) -> list[MarketEvent]`.

- [ ] **Step 1: Write failing tests**

```python
def test_event_preserves_actual_previous_forecast_and_revised_values():
    event = build_market_events([calendar_row], as_of=AS_OF)[0]
    assert event.actual == "0.0%"
    assert event.forecast == "+0.3%"
    assert event.previous == "+0.2%"


def test_future_event_is_excluded_from_report_cutoff():
    events = filter_events_as_of([past_event, future_event], AS_OF)
    assert events == [past_event]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/daily_report/test_events.py tests/daily_report/test_event_cutoff.py -q`
Expected: FAIL because event normalization and cutoff filtering are not implemented.

- [ ] **Step 3: Implement event normalization**

Normalize calendar actual, forecast, previous and revised values without coercing unknown values to zero. Normalize SEC filing date, company, form type, title and URL. Normalize Fed items from official feeds. Preserve event source time and source URL.

- [ ] **Step 4: Add cutoff and deduplication**

Filter by source time at or before `as_of`, deduplicate by stable event ID, and preserve the earliest authoritative source when duplicate news records describe the same event. Return a source-status entry when a source is unavailable.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/daily_report/test_events.py tests/daily_report/test_event_cutoff.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/daily_messenger/daily_report/events.py src/daily_messenger/etl/fetchers/events.py src/daily_messenger/etl/fetchers/edgar.py src/daily_messenger/common/news_contract.py tests/daily_report
git commit -m "feat: add point-in-time market events"
```

### Task 4: Add research bundle providers and evidence validation

**Files:**
- Create: `src/daily_messenger/daily_report/research.py`
- Create: `src/daily_messenger/daily_report/validation.py`
- Create: `src/daily_messenger/daily_report/providers/__init__.py`
- Create: `src/daily_messenger/daily_report/providers/openai_compatible.py`
- Modify: `src/daily_messenger/etl/fetchers/ai_news_gemini.py`
- Test: `tests/daily_report/test_research.py`
- Test: `tests/daily_report/test_validation.py`

**Interfaces:**
- Consumes: `MarketFact`, `MarketEvent`, provider configuration and narrow research jobs.
- Produces: `ResearchJob`, `ResearchBundle`, `run_research_job(job, facts, events, provider)`, and `validate_research_bundle(bundle, facts, events, as_of) -> ValidationResult`.

- [ ] **Step 1: Write failing tests**

```python
def test_validator_rejects_claim_with_unknown_evidence():
    bundle = bundle_with_claim(evidence_ids=["missing.fact"])
    result = validate_research_bundle(bundle, facts=[], events=[], as_of=AS_OF)
    assert result.errors == ["unknown_evidence:missing.fact"]


def test_validator_rejects_source_after_cutoff():
    bundle = bundle_with_claim(source_time=AS_OF + timedelta(minutes=1))
    result = validate_research_bundle(bundle, facts=FACTS, events=EVENTS, as_of=AS_OF)
    assert "source_after_cutoff" in result.errors


def test_conflicting_model_number_does_not_replace_fact():
    report_inputs = apply_research_bundle(FACTS, bundle_with_conflicting_number())
    assert report_inputs.facts == FACTS
    assert "fact_conflict" in report_inputs.warnings
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/daily_report/test_research.py tests/daily_report/test_validation.py -q`
Expected: FAIL because job execution and evidence validation are not implemented.

- [ ] **Step 3: Implement provider-neutral jobs**

Define `ResearchJob(kind, prompt_version, as_of, inputs)` and `ResearchProvider.generate(job) -> Mapping[str, Any]`. Add the existing Gemini path and an OpenAI-compatible adapter that can target DeepSeek without embedding credentials in code. The adapter must return a structured payload, provider metadata, attempts and error codes. Implement narrow jobs for market driver, top mover catalyst, macro, Fed and company news.

- [ ] **Step 4: Implement validator**

Validate evidence IDs, source URLs, source times, confidence enum, claim count, numeric references and allowed report cutoff. Mark provider failure as degraded and leave deterministic facts unchanged. Return errors, warnings, accepted claims and source coverage metrics.

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/daily_report/test_research.py tests/daily_report/test_validation.py -q`
Expected: PASS.
Run: `uv run ruff check src/daily_messenger/daily_report`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/daily_messenger/daily_report src/daily_messenger/etl/fetchers/ai_news_gemini.py tests/daily_report
git commit -m "feat: validate evidence-linked research bundles"
```

### Task 5: Assemble and render a validated daily report

**Files:**
- Create: `src/daily_messenger/daily_report/pipeline.py`
- Create: `src/daily_messenger/daily_report/render.py`
- Modify: `src/daily_messenger/digest/make_daily.py`
- Modify: `src/daily_messenger/cli.py`
- Test: `tests/daily_report/test_pipeline.py`
- Test: `tests/daily_report/test_render.py`
- Test: `tests/daily_report/test_idempotency.py`

**Interfaces:**
- Consumes: normalized facts, events, validated research bundle and existing artifact receipt helpers.
- Produces: `run_daily_report(as_of, output_dir, provider_config) -> DailyReport`, `render_markdown(report) -> str`, and CLI commands `dm market-facts`, `dm market-events`, `dm research`, `dm daily-report`.

- [ ] **Step 1: Write failing tests**

```python
def test_pipeline_keeps_facts_when_research_provider_fails(tmp_path):
    report = run_daily_report(AS_OF, tmp_path, provider_config=failing_provider)
    assert report.source_status["research"].quality == "degraded"
    assert report.sections[0].facts


def test_second_run_reuses_same_artifact_hash(tmp_path):
    first = run_daily_report(AS_OF, tmp_path, provider_config=fixture_provider)
    second = run_daily_report(AS_OF, tmp_path, provider_config=fixture_provider)
    assert first.run_id == second.run_id
    assert first.content_hash == second.content_hash
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/daily_report/test_pipeline.py tests/daily_report/test_render.py tests/daily_report/test_idempotency.py -q`
Expected: FAIL because the pipeline and CLI commands do not exist.

- [ ] **Step 3: Implement pipeline stages**

Implement `fetch -> normalize -> events -> research -> validate -> report`. Save each stage as a dated, immutable artifact. On rerun, reuse valid stage artifacts and retry only failed stages. Refuse to publish a report if validation errors exist, while allowing a report with explicit degraded sections when only optional sources fail.

- [ ] **Step 4: Implement renderer and CLI**

Render sections for market performance, drivers, macro/Fed, company news, gainers, losers and data gaps. Every explanatory paragraph must include its evidence IDs in machine-readable report data. Add CLI help, date and output-directory options, and keep existing commands backward compatible.

- [ ] **Step 5: Run tests and snapshot checks**

Run: `uv run pytest tests/daily_report -q`
Expected: PASS.
Run: `uv run python -m daily_messenger.cli --help`
Expected: Existing commands plus the four new commands are listed.

- [ ] **Step 6: Commit**

```bash
git add src/daily_messenger/daily_report src/daily_messenger/digest/make_daily.py src/daily_messenger/cli.py tests/daily_report
git commit -m "feat: assemble validated market daily report"
```

### Task 6: Add public artifact fixtures, documentation, and CI checks

**Files:**
- Create: `tests/fixtures/public/daily_report.json`
- Create: `tests/daily_report/test_public_artifact.py`
- Modify: `docs/contracts.md`
- Modify: `docs/architecture.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `project_tools/check_all.py`

**Interfaces:**
- Consumes: `DailyReport` artifact and the CLI from Task 5.
- Produces: documented public schema, fixture-based contract tests, and a check-all scope for daily report artifacts.

- [ ] **Step 1: Write failing fixture tests**

```python
def test_public_daily_report_contains_no_credentials(public_daily_report):
    serialized = json.dumps(public_daily_report)
    assert "API_KEY" not in serialized
    assert "auth.json" not in serialized


def test_public_daily_report_has_source_and_cutoff(public_daily_report):
    assert public_daily_report["as_of"]
    assert all(claim["evidence_ids"] for claim in public_daily_report["claims"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/daily_report/test_public_artifact.py -q`
Expected: FAIL because the fixture and public contract checks do not exist.

- [ ] **Step 3: Add fixture and documentation**

Document field definitions, source precedence, cutoff behavior, degraded states, CLI examples and the boundary between platform, deploy and Pages. Update the root README and AGENTS instructions in clear Chinese where appropriate, keeping command names and code identifiers unchanged.

- [ ] **Step 4: Integrate check-all**

Add the daily report contract tests to the existing scoped check without changing unrelated checks. Ensure public export scripts include only validated `daily_report.json` and its receipt metadata.

- [ ] **Step 5: Run full validation**

Run: `uv run pytest tests/daily_report tests/test_research_artifact_boundary.py -q`
Expected: PASS.
Run: `uv run ruff check .`
Expected: PASS.
Run: `uv run ruff format --check .`
Expected: PASS.
Run: `uv run ty check`
Expected: PASS or only the repository’s existing documented external-import allowances.
Run: `uv run python project_tools/check_all.py --scope all`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/public/daily_report.json tests/daily_report docs/contracts.md docs/architecture.md README.md AGENTS.md project_tools/check_all.py
git commit -m "docs: document daily report contracts and checks"
```

### Task 7: Shadow-run acceptance and handoff to deployment

**Files:**
- Create: `docs/how-to/daily-report-shadow-run.md`
- Modify: `docs/how-to/daily-report-shadow-run.md`
- Test: `tests/daily_report/test_shadow_run.py`

**Interfaces:**
- Consumes: validated platform artifacts and existing deployment receipt conventions.
- Produces: a five-session shadow-run procedure and an explicit handoff contract for `quant-intel-deploy` and `market-intel-pages`.

- [ ] **Step 1: Write the shadow-run test**

```python
def test_shadow_run_records_source_coverage_and_degraded_sections(shadow_run):
    result = shadow_run(date="2026-09-18")
    assert result.artifact_path.endswith("daily_report.json")
    assert result.source_coverage >= 0
    assert result.degraded_sections == ["research"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/daily_report/test_shadow_run.py -q`
Expected: FAIL until the shadow-run helper and runbook are added.

- [ ] **Step 3: Implement shadow-run reporting**

Record artifact path, hash, source coverage, validation errors, provider latency, missing sections and publish decision. Keep the output local and do not alter production timers or Pages during the platform MVP.

- [ ] **Step 4: Document handoff**

Document the exact input directory, schema version, command invocation, retry behavior, failure states and rollback rule that the deploy repository must implement. Document that Pages consumes only the validated public artifact.

- [ ] **Step 5: Run the shadow test and the full suite**

Run: `uv run pytest tests/daily_report/test_shadow_run.py -q`
Expected: PASS.
Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/how-to/daily-report-shadow-run.md tests/daily_report/test_shadow_run.py
git commit -m "docs: define daily report shadow run handoff"
```

## Execution Notes

本计划只覆盖平台仓库的首个可测试增量。平台通过五到十个交易日 shadow run 后，另开 `quant-intel-deploy` 计划接入 Hermes/systemd、凭据、重试和发布回执，再开 `market-intel-pages` 计划消费 `daily_report.json` 并展示来源和降级状态。不要在平台 MVP 中跨仓库修改生产调度或页面。
