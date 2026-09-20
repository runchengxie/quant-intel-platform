# Retire Owner Submodules Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the market-intel owner-submodule retirement branch internally consistent, verify the research-workspace boundary update, and merge both changes into their respective `main` branches.

**Architecture:** `market-intel` remains a sibling consumer/operations repository. It consumes versioned artifacts and public CLIs, while `research-workspace` owns DailyWatch20, HotSector, factor, experiment, and strategy implementations. Retired market-intel entrypoints either disappear or fail explicitly without being scheduled.

**Tech Stack:** Python 3.12+, pytest, Ruff, ty, Bash, PowerShell, GitHub CLI, Git worktrees.

**Spec:** `docs/boundary-contract.md`, `docs/daily-schedule.md`, and `research-workspace/docs/market-intel-owner-boundary.md`.

## Global Constraints

- Do not restore any of the three retired git submodules.
- Do not reintroduce factor, Hermite, walk-forward, ablation, or AI-ranking implementations into `market-intel`.
- DailyWatch20 delivery consumes the owner artifact and receipt; it does not calculate or rerank selections locally.
- Preserve an explicit tombstone only where stale deployment configuration must fail closed.
- Run the full repository quality gate before merge; do not claim completion from partial checks.

### Task 1: Repair deleted-module test and runtime imports

**Files:**
- Modify: `tests/test_a_share_factor_daily_clean_resolution.py`
- Modify: `src/a_share_daily/d11_h5_shadow_delivery.py`
- Modify: `tests/test_d11_h5_shadow_delivery.py` if its target-resolution fixture requires the new API
- Inspect and update: `src/a_share_daily/deploy_check/constants.py`

- [ ] **Step 1: Write or update failing tests** so deleted modules are no longer imported and D11-H5 resolves delivery targets through the surviving shared target helper.
- [ ] **Step 2:** Run the focused tests and confirm failure is caused by the stale import/API.
- [ ] **Step 3: Implement the smallest import/API correction without restoring retired code.
- [ ] **Step 4: Run the focused tests and confirm they pass.
- [ ] **Step 5: Commit the focused fix.

### Task 2: Remove remaining retired production references

**Files:**
- Modify: `src/a_share_daily/pipeline.py`
- Modify: `scripts/morning_pipeline.sh`
- Modify: `scripts/windows/morning_pipeline.ps1`
- Modify: `src/a_share_daily/deploy_check/constants.py`
- Modify: affected supervisor/recovery scripts and tests

- [ ] **Step 1: Add regression assertions that the scheduled path uses only owner artifacts and that retired submodule paths are not required.
- [ ] **Step 2: Run those tests to verify the current branch fails.
- [ ] **Step 3: Make optional research inputs non-blocking and remove deleted script/timer names from active deploy checks; retain only explicit fail-closed tombstone behavior where needed.
- [ ] **Step 4: Run focused producer, supervisor, and deployment tests.
- [ ] **Step 5: Commit the production-boundary fix.

### Task 3: Reconcile documentation and quality metadata

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/boundary-contract.md`
- Modify: `docs/data-ownership.md`
- Modify: `docs/workflows.md`
- Modify: `docs/maintenance-scripts.md`
- Modify: `docs/configuration.md`
- Modify: `docs/new-machine-setup.md`
- Modify: `docs/roadmap.md` and `docs/refactor-plan-etl-report.md` where they describe current code rather than historical records
- Modify: Ruff/formatting issues in files touched by the retirement

- [ ] **Step 1: Add or update repository scans/tests for current file and timer inventories.
- [ ] **Step 2: Run the scan and record every remaining active reference.
- [ ] **Step 3: Update current-state documentation and format/lint configuration without rewriting historical records unnecessarily.
- [ ] **Step 4: Run Ruff, format check, ty, shell syntax, and targeted tests.
- [ ] **Step 5: Commit the documentation and quality cleanup.

### Task 4: Verify both repositories and integrate

**Files:**
- No production files; use the two isolated worktrees and GitHub PRs #115 and #271.

- [ ] **Step 1: Run the complete `market-intel` test and quality commands on the final branch.
- [ ] **Step 2: Run the complete `research-workspace` checks relevant to the owner-boundary PR.
- [ ] **Step 3: Push both PR branches and confirm GitHub reports green checks and mergeable state.
- [ ] **Step 4: Merge PR #271 first so the research owner boundary lands before market-intel cleanup.
- [ ] **Step 5: Merge PR #115 into `market-intel/main`.
- [ ] **Step 6: Verify both `main` branches and delete only the two merged feature branches.
