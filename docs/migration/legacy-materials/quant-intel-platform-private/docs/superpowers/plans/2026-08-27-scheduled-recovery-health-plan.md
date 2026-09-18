# Scheduled Recovery Health Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent scheduled recovery from alerting on expected waits or healthy in-flight jobs, while adding enough runtime evidence and serialization to diagnose genuinely stuck publication runs.

**Architecture:** Keep the existing recovery DAG and business-date gates. Add an explicit alertability policy around stage statuses, record systemd runtime evidence when a service is active, and use a non-blocking process lock around the current-contract publisher. Treat expected deferrals as successful reconciliation with a separate deferred count.

**Tech Stack:** Python 3.11, pytest, Bash, systemd user services, `flock`.

**Spec:** User-approved requirements in the conversation on 2026-08-27.

## Global Constraints

- Preserve the evening report source window at 19:20 Asia/Shanghai.
- Do not alter existing business-date targets or delivery-window authorization.
- Only hard failure states may trigger a notification.
- Preserve unrelated worktree changes.
- Use tests before production changes for behavior changes.

---

### Task 1: Define alertable versus expected recovery states

**Files:**
- Modify: `src/ops_common/scheduled_recovery.py`
- Test: `tests/test_scheduled_recovery.py`

**Interfaces:**
- Add a small status-policy helper used by fingerprinting and notification formatting.
- Preserve `reconcile()` return shape and existing stage status names.

- [ ] **Step 1: Write failing tests** for an active service and a pre-window evening report proving neither sends an alert and that the receipt records expected/deferred state counts.
- [ ] **Step 2: Run the focused tests** with `pytest tests/test_scheduled_recovery.py -q` and confirm the new assertions fail against current behavior.
- [ ] **Step 3: Implement the minimal policy** so `in_progress`, `waiting_source_window`, `waiting_delivery_window`, `not_applicable`, and `blocked_dependency` are excluded from hard-failure fingerprints/alert text where the dependency is merely deferred.
- [ ] **Step 4: Run the focused tests** and confirm all scheduled-recovery tests pass.
- [ ] **Step 5: Refactor only after green** to keep the policy names centralized and readable.

### Task 2: Add runtime evidence and completion-pending classification

**Files:**
- Modify: `src/ops_common/scheduled_recovery.py`
- Test: `tests/test_scheduled_recovery.py`

**Interfaces:**
- Extend `_systemd_probe()` with `ExecMainStartTimestamp`, `ExecMainExitTimestamp`, and `InvocationID` when available.
- Record `runtime_seconds`, `runtime_timeout_seconds`, and `completion_pending` evidence for active services.

- [ ] **Step 1: Write failing tests** for an active service inside the grace period and an active service beyond the grace period.
- [ ] **Step 2: Run those tests** and verify the new runtime fields/status expectations fail.
- [ ] **Step 3: Implement a configurable grace period** with a conservative default of 45 minutes, classifying an active stale service as `in_progress` within the grace period and `stuck_in_progress` after it.
- [ ] **Step 4: Add receipt fields** for service start/exit/invocation data and `completion_pending` when the job has produced the expected output but not its final release receipt.
- [ ] **Step 5: Run focused and existing recovery tests** and confirm no existing dependency ordering behavior changes.

### Task 3: Serialize current-contract publication

**Files:**
- Modify: `scripts/publish_a_share_current.sh`
- Test: `tests/test_report_recovery_scripts.py` or a new focused script test

**Interfaces:**
- Add `flock` protection using a deployment-local lock file.
- Preserve the script's exit code and all existing publication CLI arguments.

- [ ] **Step 1: Write a failing shell-content test** requiring a lock before any destructive output-directory preparation and a clear busy exit path.
- [ ] **Step 2: Run the test** and verify the current script does not satisfy the serialization contract.
- [ ] **Step 3: Add the non-blocking lock** with a stable path under the data root and exit code 75 when another publisher owns it.
- [ ] **Step 4: Run `bash -n` and the focused script tests** to verify syntax and ordering.
- [ ] **Step 5: Confirm the lock does not change normal successful execution semantics.**

### Task 4: Full verification and handoff

**Files:**
- No production files unless verification exposes a regression.

- [ ] **Step 1: Run the complete relevant test suite** covering scheduled recovery and shell scripts.
- [ ] **Step 2: Review the diff** and confirm unrelated existing changes remain untouched.
- [ ] **Step 3: Report exact files, tests, and any remaining operational caveat.**
