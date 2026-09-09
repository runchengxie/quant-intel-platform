# Quant Production Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the current private production Quant behavior on the new public `main` architecture and cut production over only after five consecutive trading days of verified parity.

**Architecture:** Keep ownership split across `quant-intel-deploy` (orchestration), `quant-intel-platform` (reporting, validation, delivery contracts), `quant-research` (strategies and research artifacts), and `quant-market-data-platform` (data ownership). Use versioned artifacts and receipts between repositories; do not copy private release history into public `main`.

**Tech Stack:** Python 3.11+, Bash, uv, pytest, systemd user units, Hermes jobs, Feishu/Lark CLI, Parquet/JSON/Markdown artifacts.

**Spec:** `docs/superpowers/specs/2026-09-09-quant-production-parity-design.md`

## Global Constraints

- The canonical data root is `/home/richard/data/quant/market-data-platform`.
- Production code must not infer paths from retired `research-workspace` or `market-intel` directories.
- Every code change starts in an isolated worktree and ends in a PR to `main`.
- Retired features remain explicitly marked retired; they are not silently reactivated.
- New and old implementations write to separate output namespaces during dual-run.
- A delivery is successful only when the canonical receipt validates kind, dates, generated time, success, and target route.
- Production cutover requires five consecutive trading days with no unexplained parity differences.

## Repository and PR Map

| Track | Repository | Deliverable |
|---|---|---|
| A | `quant-market-data-platform` | canonical asset and data freshness contracts |
| B | `quant-research` | strategy/research artifact contracts and replayable runners |
| C | `quant-intel-platform` | report, receipt, delivery, and watchdog behavior |
| D | `quant-intel-deploy` | scheduler/orchestration and production boundary |
| E | all four | dual-run fixtures, comparison, and cutover evidence |

Each track uses its own worktree and PR. A later track may consume only merged public interfaces from earlier tracks.

### Task 1: Freeze production fixtures and parity comparison schema

**Files:**
- Create: `tests/parity/fixtures/README.md`
- Create: `tests/parity/schema.py`
- Create: `tests/parity/compare.py`
- Create: `tests/parity/test_compare.py`
- Modify: `docs/superpowers/artifacts/2026-09-09-quant-production-parity-inventory.md`

**Interfaces:**
- `ParityArtifact` consumes a JSON artifact path and returns a normalized mapping.
- `compare_artifacts(expected: Path, actual: Path, *, ignored_fields: set[str]) -> list[str]` returns stable difference descriptions.
- The comparison layer must compare dates, schema versions, row/symbol counts, receipt identity, status, and file inventories; generated timestamps and message IDs are ignored unless explicitly requested.

- [ ] **Step 1: Write failing comparison tests**

```python
def test_compare_ignores_generated_at_and_message_id(tmp_path):
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    expected.write_text('{"trade_date":"20260908","generated_at":"a","message_id":"x"}\n')
    actual.write_text('{"trade_date":"20260908","generated_at":"b","message_id":"y"}\n')
    assert compare_artifacts(expected, actual, ignored_fields={"generated_at", "message_id"}) == []

def test_compare_reports_trade_date_difference(tmp_path):
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    expected.write_text('{"trade_date":"20260908"}\n')
    actual.write_text('{"trade_date":"20260909"}\n')
    assert "trade_date" in compare_artifacts(expected, actual, ignored_fields=set())[0]
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `uv run pytest -q tests/parity/test_compare.py`

Expected: FAIL because `compare_artifacts` is not implemented.

- [ ] **Step 3: Implement normalization and comparison**

Implement deterministic JSON loading, recursive field comparison, sorted list comparison for declared set-like fields, and readable path-based difference messages. Do not compare wall-clock timestamps unless the caller omits them from `ignored_fields`.

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest -q tests/parity/test_compare.py`

Commit: `test: add production parity artifact comparator`

### Task 2: Formalize canonical data and receipt contracts

**Files:**
- Modify: `quant-market-data-platform/src/market_data_platform/research_views/daily_watch20_data.py`
- Modify: `quant-research/src/market_data_platform/research_views/daily_watch20_data.py`
- Test: `quant-market-data-platform/tests/test_daily_watch20_data_owner.py`
- Test: `quant-research/tests/market_data_platform/test_daily_watch20_data_owner.py`
- Create: `quant-market-data-platform/tests/test_materialized_operational_receipt.py`

**Interfaces:**
- `resolve_daily_watch20_assets(data_root, minute_dataset="tushare") -> DailyWatch20Assets` remains the public resolver.
- A valid TuShare receipt must have the operational schema, published status, provider `tushare`, an existing declared output directory, and both alias mutation flags false.
- The resolver returns the declared version directory, supporting both symlink and materialized alias layouts.

- [ ] **Step 1: Add tests for symlink and materialized alias layouts**
- [ ] **Step 2: Run `uv run pytest -q tests/test_daily_watch20_data_owner.py tests/test_materialized_operational_receipt.py` and verify the new materialized case fails on the baseline.**
- [ ] **Step 3: Implement the resolver in each owner checkout with the same validation rules.**
- [ ] **Step 4: Run both repository test sets and commit one PR per repository.**

Commit messages: `fix: accept materialized TuShare minute receipts`.

### Task 3: Make Watch20 research output replayable and versioned

**Files:**
- Inspect/modify: `quant-research/src/strategy_app/daily_watch20/pipeline.py`
- Inspect/modify: `quant-research/src/strategy_app/daily_watch20/publish_api.py`
- Inspect/modify: `quant-research/scripts/run_daily_watch20_runtime.py`
- Modify: `quant-intel-deploy/scripts/refresh_daily_watch20_quant_research.sh`
- Create: `quant-research/tests/strategy_app/test_daily_watch20_replay.py`

**Interfaces:**
- A run consumes `data_root`, `source_date`, `candidate_pool_mode`, model-window parameters, and publication tier.
- A run produces a versioned run directory, `latest` pointer, `watchlist_20.csv/json`, `candidate_scores.csv`, model metadata, topic summary, and `selection_receipt.json`.
- Re-running with the same frozen inputs must produce the same selected symbols and receipt identity, except for generated timestamps and run UUIDs.

- [ ] **Step 1: Add a frozen-input replay fixture containing a small daily/minute dataset and expected 20-symbol selection.**
- [ ] **Step 2: Add a replay test that invokes the public runner with `candidate_pool_mode="all_market"` and asserts source date, signal date, symbol count, and receipt status.**
- [ ] **Step 3: Run the replay test against the current implementation and record any legitimate model nondeterminism explicitly.**
- [ ] **Step 4: Make publication atomic and refuse replacement of a non-symlink `latest` unless it is an explicitly archived legacy directory.**
- [ ] **Step 5: Run the full DailyWatch20 test subset and commit.**

Commit: `test: make DailyWatch20 replay contract explicit` followed by `fix: publish replayable DailyWatch20 artifacts` if implementation changes are required.

### Task 4: Rebuild report manifest and content parity

**Files:**
- Inspect/modify: `quant-intel-platform/src/a_share_daily/morning_report.py`
- Inspect/modify: `quant-intel-platform/src/a_share_daily/evening_manifest.py`
- Inspect/modify: `quant-intel-platform/src/a_share_daily/report_dataset_refresh.py`
- Inspect/modify: `quant-intel-platform/src/a_share_daily/cross_market.py`
- Create: `quant-intel-platform/tests/parity/test_morning_report_parity.py`
- Create: `quant-intel-platform/tests/parity/test_evening_report_parity.py`

**Interfaces:**
- Morning generation accepts a manifest path, optional news payload, and output path; it must preserve report date identity and structured sections.
- Evening generation must emit a typed manifest with complete chart/artifact status.
- Missing optional data produces explicit degraded fields; it must not silently fabricate facts or change the report date.

- [ ] **Step 1: Capture one redacted production morning and evening manifest as golden fixtures.**
- [ ] **Step 2: Add tests for date identity, required sections, optional degradation, and artifact inventory.**
- [ ] **Step 3: Run focused parity tests against the current main implementation.**
- [ ] **Step 4: Implement only differences that are explained by the inventory; do not copy private release paths.**
- [ ] **Step 5: Run `uv run pytest -q tests/a_share_daily tests/parity` and commit.**

Commit: `test: define morning and evening report parity` and implementation commits as needed.

### Task 5: Unify delivery, idempotency, and watchdog behavior

**Files:**
- Inspect/modify: `quant-intel-platform/src/a_share_daily/delivery/report_delivery.py`
- Inspect/modify: `quant-intel-platform/src/a_share_daily/daily_watch20_delivery_receipt.py`
- Inspect/modify: `quant-intel-platform/src/a_share_daily/delivery/state.py`
- Inspect/modify: `quant-intel-platform/src/a_share_daily/morning_product_supervisor.py`
- Modify: `quant-intel-deploy/scripts/daily_watch20_delivery.sh`
- Modify: `quant-intel-deploy/scripts/check_daily_watch20_producer_freshness.py`
- Create: `quant-intel-platform/tests/a_share_daily/test_delivery_idempotency.py`

**Interfaces:**
- Delivery functions accept explicit report/selection paths, source date, signal date, receipt path, and dry-run flag.
- A successful send writes one canonical receipt with `kind`, `trade_date`, `signal_date`, `generated_at`, `success`, route statuses, and message IDs.
- Repeating the same idempotency key returns the existing logical delivery instead of sending a duplicate.

- [ ] **Step 1: Add tests for first send, exact retry, changed-content retry, stale receipt, and dry-run.**
- [ ] **Step 2: Run the tests and verify the baseline exposes any duplicate or stale-receipt behavior.**
- [ ] **Step 3: Implement receipt validation and idempotency without changing Feishu target selection.**
- [ ] **Step 4: Add watchdog tests for fresh artifact, stale artifact, missing receipt, failed producer, and alert suppression outside delivery window.**
- [ ] **Step 5: Run delivery/watchdog tests and commit.**

Commit: `test: cover delivery idempotency and watchdog contracts` followed by implementation commits.

### Task 6: Align deploy orchestration and scheduler boundaries

**Files:**
- Modify: `quant-intel-deploy/scripts/morning_pipeline.sh`
- Modify: `quant-intel-deploy/scripts/evening_pipeline.sh`
- Modify: `quant-intel-deploy/scripts/morning_product_supervisor.sh`
- Modify: `quant-intel-deploy/scripts/reconcile_scheduled_runs.sh`
- Modify: `quant-intel-deploy/scripts/lib/deployment_paths.sh`
- Test: `quant-intel-deploy/smoke_tests/test_scheduler_templates.py`
- Test: `quant-intel-deploy/smoke_tests/test_public_boundary.py`

**Interfaces:**
- Every scheduler entrypoint loads the canonical paths file before resolving roots.
- No entrypoint may infer `MDP_DIR`, research roots, or data roots from retired workspace paths.
- Late recovery defaults to artifact-only/audit-only; `MARKET_INTEL_FORCE_REPORT_DELIVERY=1` is required for explicit historical resend.

- [ ] **Step 1: Add smoke assertions for every active unit's ExecStart, WorkingDirectory, and root environment.**
- [ ] **Step 2: Run the smoke tests against the current units and capture the active unit list.**
- [ ] **Step 3: Implement missing boundary checks and explicit exit-code propagation.**
- [ ] **Step 4: Run shell syntax, smoke tests, and a no-send morning/evening rehearsal.**
- [ ] **Step 5: Commit and open the deploy PR.**

Commit: `test: enforce new Quant scheduler boundaries` followed by implementation commits.

### Task 7: Build dual-run and five-day verification harness

**Files:**
- Create: `quant-intel-platform/tests/parity/run_parity.py`
- Create: `quant-intel-platform/tests/parity/README.md`
- Create: `docs/superpowers/artifacts/parity-runs/README.md`
- Modify: `docs/superpowers/artifacts/2026-09-09-quant-production-parity-inventory.md`

**Interfaces:**
- `run_parity.py --source-date YYYYMMDD --signal-date YYYYMMDD --old-root PATH --new-root PATH --output-root PATH` runs both implementations against frozen inputs and emits a comparison manifest.
- The comparison manifest records code commits, data snapshot identifiers, artifact diffs, receipt diffs, and unexplained differences.
- A run returns nonzero when any mandatory artifact or receipt differs outside the declared tolerance.

- [ ] **Step 1: Add a CLI test that compares two fixture directories and rejects a changed mandatory field.**
- [ ] **Step 2: Implement the comparison runner using the Task 1 comparator.**
- [ ] **Step 3: Run one historical date and one current controlled date with no Feishu send.**
- [ ] **Step 4: Record five trading-day results and require zero unexplained mandatory differences.**
- [ ] **Step 5: Commit the harness and evidence template.**

Commit: `feat: add Quant production parity runner`.

### Task 8: Controlled cutover and private-line retirement

**Files:**
- Modify: systemd user unit templates under `quant-intel-deploy/scripts/systemd/`
- Modify: Hermes canonical path/env setup
- Create: `docs/superpowers/artifacts/quant-production-cutover-YYYY-MM-DD.md`
- Modify: `docs/production-migration.md`

- [ ] **Step 1: Verify all non-retired inventory entries are `verified`.**
- [ ] **Step 2: Switch one product at a time to the new main commit and run postflight verification.**
- [ ] **Step 3: Keep the private line available as a read-only rollback archive during the observation window.**
- [ ] **Step 4: After five clean trading days, remove active references to the private line and archive its release metadata.**
- [ ] **Step 5: Run final path audit, delivery receipt audit, scheduler audit, and rollback rehearsal.**
- [ ] **Step 6: Commit cutover evidence and close the parity project only after all gates pass.**

Commit: `docs: record Quant production cutover`.

## Self-Review

- The inventory covers operations, research, reports, delivery, data, and retired capabilities.
- Each implementation task names files, interfaces, tests, and commit boundaries.
- No task asks an implementer to blindly copy the private repository history.
- The plan requires dual-run evidence and five trading days before cutover.
- The only intentional external side effect is the final controlled production cutover after all PRs and verification gates pass.
