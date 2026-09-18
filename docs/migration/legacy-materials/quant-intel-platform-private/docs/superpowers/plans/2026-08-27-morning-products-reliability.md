# Morning Products Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure the morning pipeline generates DailyWatch20 and D11-H5 for the current signal date after required data refreshes, and exposes actionable failure details.

**Architecture:** The morning pipeline remains the source of truth for the current source/signal dates. DailyWatch20 receives those dates explicitly, while the supervisor continues to validate and recover with fail-closed semantics. D11-H5 failures are retained in the pipeline receipt/alert without weakening delivery validation.

**Tech Stack:** Bash, Python, systemd user units, pytest, uv.

**Spec:** The user-approved repair direction in the conversation on 2026-08-27.

## Global Constraints

- Never publish a stale DailyWatch20 artifact.
- Optional product failures must not block the mandatory morning report.
- Recovery must be bounded and use the current signal date.
- Existing unrelated worktree changes must be preserved.

---

### Task 1: Make DailyWatch20 date handling explicit

**Files:**
- Modify: `scripts/refresh_daily_watch20.sh`
- Modify: `src/a_share_daily/morning_product_supervisor.py`
- Test: `tests/test_daily_watch20_producer_script.py`
- Test: `tests/test_morning_product_supervisor.py`

- [ ] Add tests proving the producer can receive an explicit signal date and that supervisor recovery passes it through.
- [ ] Run the targeted tests and observe the expected failure.
- [ ] Implement the smallest explicit-date interface and preserve current automatic behavior for standalone legacy callers.
- [ ] Run the targeted tests again.

### Task 2: Order morning data refresh before optional products

**Files:**
- Modify: `scripts/morning_pipeline.sh`
- Test: `tests/test_morning_pipeline.sh` or the closest existing pipeline test file.

- [ ] Add a regression test or shell-level assertion that DailyWatch20 generation occurs after report dataset refresh and before hotsector delivery.
- [ ] Run it red.
- [ ] Invoke DailyWatch20 with the pipeline’s explicit source/signal dates after report dataset refresh, retaining fail-closed behavior.
- [ ] Run the regression test and relevant existing tests.

### Task 3: Preserve D11-H5 failure details

**Files:**
- Modify: `scripts/morning_pipeline.sh`
- Modify: `src/a_share_daily/d11_h5_shadow_delivery.py` only if needed to expose structured errors.
- Test: existing morning pipeline and D11-H5 delivery tests.

- [ ] Add a test that a failed optional D11-H5 invocation includes a bounded error summary in the alert/receipt context.
- [ ] Run it red.
- [ ] Capture stderr/status without changing the optional-product non-blocking contract.
- [ ] Run D11-H5 and pipeline regression tests.

### Task 4: Verify and document operational recovery

**Files:**
- Modify: `docs/daily-schedule.md` if the installed order/timing changes.

- [ ] Run focused tests, shell syntax checks, and the relevant full test subset.
- [ ] Inspect the diff and verify unrelated changes remain untouched.
- [ ] Document the one-shot backfill command for today without executing external delivery unless explicitly requested.
