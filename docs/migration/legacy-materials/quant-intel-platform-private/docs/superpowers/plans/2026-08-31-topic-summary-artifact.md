# DailyWatch20 Topic Summary Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a validated `topic_summary.json` beside each DailyWatch20 production artifact, render it in `market-intel`, and make its watchdog check optional by default but fail-closed when explicitly required.

**Architecture:** `strategy-pipeline` aggregates the already-selected DailyWatch20 rows by their owner-provided `theme` and records the summary in the same immutable run directory and selection receipt. `market-intel` validates and renders that artifact without recalculating strategy scores; its watchdog checks the same `latest` path under an opt-in requirement flag.

**Tech Stack:** Python 3.12+, pandas, matplotlib, pytest, JSON artifacts, systemd-compatible shell/Python watchdog.

**Spec:** `market-intel/docs/superpowers/specs/2026-08-31-topic-summary-artifact-design.md`

## Global Constraints

- Do not restore `hot-sector-screener` or read the retired `candidate_universe.json` on the default production path.
- The topic summary uses only published DailyWatch20 `theme` and `tracking_weight` fields.
- `topic_summary.json` is published beside `watchlist_20.json` in the same immutable run directory.
- Missing or invalid topic artifacts remain a report-level degradation unless `WATCHDOG_REQUIRE_TOPIC_SUMMARY=1`.
- Cross-repository communication uses the versioned artifact and receipt contract, not business-code imports.
- Run tests from each repository’s own worktree and do not add cross-repository test execution to `market-intel`.

### Task 1: Add the producer-side topic aggregation contract

**Files:**
- Create: `/home/richard/code/.worktrees/strategy-pipeline-topic-summary/src/strategy_pipeline/daily_watch20_topic_summary.py`
- Test: `/home/richard/code/.worktrees/strategy-pipeline-topic-summary/tests/test_daily_watch20_topic_summary.py`

**Interfaces:**
- Produces `build_topic_summary(watchlist: pandas.DataFrame, *, source_date: str, signal_date: str) -> dict[str, Any]`.
- The returned mapping contains `schema_version`, `artifact_type`, `source_date`, `signal_date`, `source`, `aggregation`, `topics`, and `quality`.

- [ ] **Step 1: Write the failing aggregation tests**

```python
def test_build_topic_summary_aggregates_tracking_weights_and_ranks_topics():
    frame = pd.DataFrame([
        {"theme": "通信与计算", "tracking_weight": 0.25},
        {"theme": "半导体与电子", "tracking_weight": 0.50},
        {"theme": "通信与计算", "tracking_weight": 0.25},
    ])

    summary = build_topic_summary(frame, source_date="20260828", signal_date="20260831")

    assert summary["schema_version"] == "daily_watch20.topic_summary.v1"
    assert summary["topics"] == [
        {"topic": "半导体与电子", "count": 1, "weight": 0.5, "rank": 1},
        {"topic": "通信与计算", "count": 2, "weight": 0.5, "rank": 2},
    ]
    assert summary["quality"] == {"status": "passed", "selected_count": 3, "topic_count": 2}


@pytest.mark.parametrize("frame", [pd.DataFrame(), pd.DataFrame([{"theme": "", "tracking_weight": 1.0}])])
def test_build_topic_summary_rejects_empty_selection_or_theme(frame):
    with pytest.raises(ValueError, match="theme|watchlist"):
        build_topic_summary(frame, source_date="20260828", signal_date="20260831")


def test_build_topic_summary_rejects_invalid_weights():
    frame = pd.DataFrame([{"theme": "主题", "tracking_weight": float("nan")}])
    with pytest.raises(ValueError, match="tracking_weight"):
        build_topic_summary(frame, source_date="20260828", signal_date="20260831")
```

- [ ] **Step 2: Run the focused tests and verify the expected missing-symbol failure**

Run: `cd /home/richard/code/.worktrees/strategy-pipeline-topic-summary && uv run --locked --extra dev python -m pytest tests/test_daily_watch20_topic_summary.py -q`

Expected: FAIL because `strategy_pipeline.daily_watch20_topic_summary` does not exist.

- [ ] **Step 3: Implement the minimal pure aggregation and validation**

Implement finite non-negative weight validation, required non-empty `theme`, strict date normalization, grouping by theme, count and summed weight, deterministic ordering by descending weight then ascending topic, and rank assignment. Reject a zero total weight and round serialized weights only if the exact sum remains within the contract tolerance.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run the same pytest command. Expected: PASS.

- [ ] **Step 5: Commit the producer contract**

```bash
git add src/strategy_pipeline/daily_watch20_topic_summary.py tests/test_daily_watch20_topic_summary.py
git commit -m "feat: add DailyWatch20 topic summary contract"
```

### Task 2: Publish the topic artifact and receipt hash

**Files:**
- Modify: `/home/richard/code/.worktrees/strategy-pipeline-topic-summary/src/strategy_pipeline/_daily_watch20_publish_api.py:_publish_locked`
- Modify: `/home/richard/code/.worktrees/strategy-pipeline-topic-summary/src/strategy_pipeline/daily_watch20_pipeline.py:run result wiring`
- Modify: `/home/richard/code/.worktrees/strategy-pipeline-topic-summary/src/strategy_pipeline/_daily_watch20_publish_core.py` only if the existing artifact inventory helper needs a focused extension
- Test: `/home/richard/code/.worktrees/strategy-pipeline-topic-summary/tests/test_daily_watch20_publication.py` or the existing focused publication test file that covers `_publish_locked`

**Interfaces:**
- `_publish_locked` receives the validated topic summary mapping and writes `topic_summary.json` into staging before writing `selection_receipt.json`.
- `selection_receipt["artifacts"]["topic_summary.json"]` contains the same path/bytes/SHA-256 shape as existing artifacts.

- [ ] **Step 1: Add a failing publication test**

Extend the existing publication fixture to assert that a successful run contains `topic_summary.json`, that its JSON dates match the selection receipt, and that the receipt artifact inventory hash equals the file hash.

- [ ] **Step 2: Run the focused publication test and verify it fails**

Run: `uv run --locked --extra dev python -m pytest tests/test_daily_watch20_publication.py -q` (or the exact existing test module selected after locating the publication fixture).

Expected: FAIL because the published run does not yet contain the topic artifact.

- [ ] **Step 3: Thread the summary into publication**

Build the summary from the validated delivery frame after `_select_delivery`, pass it through `DailyWatch20PublishResult` call sites, write it atomically to staging, include it in `_artifact_inventory`, and preserve the existing publication conflict and latest-symlink behavior.

- [ ] **Step 4: Run focused producer tests**

Run: `uv run --locked --extra dev python -m pytest tests/test_daily_watch20_topic_summary.py tests/test_daily_watch20_publication.py tests/test_daily_watch20_freshness.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the publication change**

```bash
git add src/strategy_pipeline tests
git commit -m "feat: publish DailyWatch20 topic summary artifact"
```

### Task 3: Add the market-intel consumer and topic chart

**Files:**
- Create or modify: `/home/richard/code/.worktrees/market-intel-topic-summary/src/a_share_daily/topic_summary.py`
- Modify: `/home/richard/code/.worktrees/market-intel-topic-summary/src/a_share_daily/charts/topic.py`
- Modify: `/home/richard/code/.worktrees/market-intel-topic-summary/src/a_share_daily/pipeline.py:step_hotsector and _run_topic_chart`
- Modify: `/home/richard/code/.worktrees/market-intel-topic-summary/src/a_share_daily/morning_report.py` if the displayed status needs the new field
- Test: `/home/richard/code/.worktrees/market-intel-topic-summary/tests/test_topic_summary.py`
- Test: `/home/richard/code/.worktrees/market-intel-topic-summary/tests/test_a_share_pipeline.py`

**Interfaces:**
- `load_topic_summary(path: Path, *, expected_source_date: str | None = None, expected_signal_date: str | None = None) -> dict[str, Any]` validates the consumer contract.
- `generate_topic(topic_summary_json_path: str, out_path: str) -> str | None` renders the new semantics: “DailyWatch20 热点主题分布”.

- [ ] **Step 1: Write failing consumer and renderer tests**

Test valid loading, wrong source date rejection, empty topics rejection, missing input degradation, and chart generation from the new schema. Assert the old `candidate_universe` format is not used by the default path.

- [ ] **Step 2: Run focused consumer tests and verify failure**

Run: `cd /home/richard/code/.worktrees/market-intel-topic-summary && uv run --locked python -m pytest tests/test_topic_summary.py tests/test_a_share_pipeline.py -q`

Expected: FAIL because the new loader and chart contract do not exist.

- [ ] **Step 3: Implement validation and rendering**

Read `A_SHARE_TOPIC_SUMMARY_INPUT` first when set, otherwise resolve `WATCHLIST20_ROOT/topic_summary.json`; validate schema, artifact type, dates, finite non-negative weights, rank ordering, and non-empty topics. Replace the topic chart’s `candidate_universe` reads with the validated `topics` list and use the explicit DailyWatch20 wording.

- [ ] **Step 4: Update manifest status without blocking the report**

Expose `topic_summary_json`, `topics`, and a clear degradation reason in the manifest. Keep the chart placeholder path and make missing/invalid input a degraded chart result, not a pipeline exception.

- [ ] **Step 5: Run focused market-intel tests and commit**

```bash
uv run --locked python -m pytest tests/test_topic_summary.py tests/test_a_share_pipeline.py tests/test_morning_report.py -q
git add src tests
git commit -m "feat: render DailyWatch20 topic summary in morning report"
```

### Task 4: Add optional/required topic watchdog admission

**Files:**
- Modify: `/home/richard/code/.worktrees/market-intel-topic-summary/scripts/check_daily_watch20_producer_freshness.py`
- Modify: `/home/richard/code/.worktrees/market-intel-topic-summary/tests/test_daily_watch20_producer_watchdog.py`
- Modify: `/home/richard/code/.worktrees/market-intel-topic-summary/docs/configuration.md`
- Modify: `/home/richard/code/.worktrees/market-intel-topic-summary/docs/operations.md`

**Interfaces:**
- `check(..., require_topic_summary: bool = False, topic_summary_root: Path | None = None)` adds the optional check without changing existing default callers.
- CLI supports `--require-topic-summary`; environment default is `WATCHDOG_REQUIRE_TOPIC_SUMMARY`.

- [ ] **Step 1: Add failing watchdog tests**

Cover: valid artifact passes when required, missing artifact returns 0 when optional, missing artifact returns 1 when required, wrong dates fail, and receipt hash mismatch fails when a receipt entry exists.

- [ ] **Step 2: Run watchdog tests and verify failure**

Run: `uv run --locked python -m pytest tests/test_daily_watch20_producer_watchdog.py -q`

Expected: FAIL because the watchdog has no topic-summary check or CLI flag.

- [ ] **Step 3: Implement the opt-in admission check**

Resolve the actual DailyWatch20 `latest` root from `WATCHLIST20_ROOT` or the data-root default, validate the topic summary against the latest data-lake source date and `as_of` signal date, verify the receipt SHA-256 entry, print a non-fatal status when optional, and append a normal watchdog problem when required.

- [ ] **Step 4: Run focused watchdog and regression tests**

Run: `uv run --locked python -m pytest tests/test_daily_watch20_producer_watchdog.py tests/test_morning_product_supervisor.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the watchdog change**

```bash
git add scripts tests docs
git commit -m "feat: optionally watchdog DailyWatch20 topic artifact"
```

### Task 5: Cross-repository documentation and follow-up migration plans

**Files:**
- Modify: `/home/richard/code/.worktrees/market-intel-topic-summary/docs/contracts.md`
- Modify: `/home/richard/code/.worktrees/strategy-pipeline-topic-summary/docs/outputs.md`
- Create: `/home/richard/code/.worktrees/market-intel-topic-summary/docs/superpowers/plans/2026-08-31-news-heat-migration.md`
- Create: `/home/richard/code/.worktrees/market-intel-topic-summary/docs/superpowers/plans/2026-08-31-analysis-and-style-bridge-migration.md`

- [ ] **Step 1: Document the artifact and deployment switch**

Document the file location, schema version, explicit `A_SHARE_TOPIC_SUMMARY_INPUT` override, `WATCHDOG_REQUIRE_TOPIC_SUMMARY` rollout sequence, and the requirement to publish producer code before enabling the required watchdog flag.

- [ ] **Step 2: Write the news-heat migration plan**

Specify moving `a_share_daily/news_heat.py` and its producer invocation into `strategy-pipeline`, preserving the existing sparse-positive contract and removing the market-intel producer dependency after a compatibility window.

- [ ] **Step 3: Write the analysis/style migration plan**

Specify migration of the calculations in `value_regime_weekly.py`, `size_style_weekly.py`, and the style-factor publication bridge, with `market-intel` retaining only artifact validation, rendering, delivery, and operational recovery.

- [ ] **Step 4: Run documentation and focused full tests**

Run the relevant contract tests in both repositories, `ruff check` for changed Python files, and the repository documentation checks applicable to changed docs.

- [ ] **Step 5: Commit documentation in each repository**

Commit producer docs and migration plans in the strategy-pipeline/research-workspace branch, and consumer docs in the market-intel branch. Do not update production symlinks or enable the required watchdog flag until both branches are merged and promoted.
