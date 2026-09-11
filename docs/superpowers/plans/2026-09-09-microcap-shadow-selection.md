# Microcap Shadow Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing smallest-400 microcap research rule into an auditable research-shadow selection artifact that supplies three candidates to Weekly Client Basket 10.

**Architecture:** The research repository owns the microcap candidate construction and writes a JSON artifact. The platform repository only validates and consumes that artifact; it does not import research code or promote the sleeve to live eligibility. The starting universe is the smallest 400 eligible A-share stocks, followed by deterministic liquidity/price-continuity ranking and explicit current tradability gates.

**Tech Stack:** Python 3.13, pandas/pyarrow, pytest, JSON artifacts, existing Weekly Client Basket contracts.

**Spec:** `docs/superpowers/specs/2026-09-09-weekly-client-basket-10-design.md`

## Global Constraints

- Microcap remains `shadow=true`, `research_only=true`, and `eligible_for_live=false`.
- The candidate pool is the smallest 400 stocks by positive total market value after hard eligibility filters.
- Selection must fail closed when fewer than three distinct valid candidates remain.
- Historical/formation-date data must not use future listing or delisting information.
- Existing user changes in the main workspaces must remain untouched.

### Task 1: Define and test the research-side selection contract

**Files:**
- Create: `/home/richard/code/quant/quant-research/.worktrees/microcap-shadow-selection/src/style_factors/microcap_shadow_selection.py`
- Create: `/home/richard/code/quant/quant-research/.worktrees/microcap-shadow-selection/tests/strategy_research/test_microcap_shadow_selection.py`

**Interfaces:**
- `build_microcap_shadow_selection(frame, signal_date, candidate_count=400, selection_count=10) -> dict`
- Input fields: `symbol`, `name`, `trade_date`, `total_mv`, `amount`, `is_st`, `is_suspended`, `list_status`, `list_date`, `delist_date`, and `next_day_valid`.
- Output fields: `schema_version`, `status`, `shadow`, `research_only`, `eligible_for_live`, `signal_date`, `candidate_pool_size`, and `positions`.

- [x] Write failing tests for hard eligibility, smallest-400 pool membership, deterministic ranking, and shadow metadata.
- [x] Run the focused tests and confirm they fail because the module is absent.
- [x] Implement the smallest deterministic selector: filter listed/non-ST/non-suspended/positive-cap/positive-amount/valid-next-day rows, rank by `amount` descending then symbol, retain the smallest-400 pool, select the requested top rows, and emit the artifact.
- [x] Run the focused tests and confirm they pass.

### Task 2: Add a research runner that materializes the artifact from the daily panel

**Files:**
- Modify: `/home/richard/code/quant/quant-research/scripts/research/experiments/style_factors/microcap_robustness_20260829.py` or add a focused sibling runner beside it.
- Modify: `/home/richard/code/quant/quant-research/tests/strategy_research/test_microcap_runner.py`

- [x] Add a runner entry point that reads the latest cleaned daily panel and instrument snapshot, computes the latest candidate pool without future rows, and writes `microcap_shadow_selection.json` plus a receipt.
- [x] Add a focused selector/runner verification for output path, signal date, and fail-closed behavior.
- [x] Run the focused runner tests and a real-data artifact build.

### Task 3: Consume the artifact in Weekly Client Basket

**Files:**
- Modify: `/home/richard/code/quant/quant-intel-platform/.worktrees/microcap-shadow-selection/src/a_share_daily/weekly_client_basket.py`
- Modify: `/home/richard/code/quant/quant-intel-platform/.worktrees/microcap-shadow-selection/tests/test_weekly_client_basket.py`

- [x] Add tests that reject a microcap artifact missing hard shadow metadata or with fewer than three positions.
- [x] Add tests that preserve microcap rank, score, names, and `research_only=true` in the composed basket.
- [x] Implement only the minimum loader/schema checks needed for the research artifact.
- [x] Run the focused platform tests and confirm they pass.

### Task 4: Generate and verify a local weekly preview

**Files:**
- No source changes unless a test exposes a contract mismatch.
- Generated output under the existing research/deploy artifact root.

- [x] Generate the current microcap shadow artifact from the latest local data.
- [x] Compose the 4/3/3 Weekly Basket locally with the current DailyWatch and Cashflow artifacts.
- [ ] Verify no selected symbol is currently delisted, ST, suspended, or duplicated; this is blocked by the pre-existing Cashflow 002071.SZ contamination.
- [ ] Run the focused and relevant full test suites.
- [ ] Review the diff, merge both branches to local `main`, and delete the temporary worktrees only after verification.
