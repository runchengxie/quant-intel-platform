# Scheduled Recovery Loop Strengthening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 45-minute recovery loop observable and actionable when it detects a persistent dependency or delivery failure.

**Architecture:** Keep the existing static recovery DAG and bounded idempotent actions. Add an atomic heartbeat/state summary on every run, and add transition-aware Feishu alerting for unresolved recovery failures so repeated 45-minute checks do not spam alerts.

**Tech Stack:** Python, systemd user timers, JSON receipts, pytest, lark-cli.

**Spec:** Existing recovery contract in `docs/daily-schedule.md` and `src/ops_common/scheduled_recovery.py`.

## Global Constraints

- Recovery actions remain restricted to the static `DEFAULT_SPECS` allow-list.
- Recovery remains dependency-ordered and fail-closed for stale or missing artifacts.
- Automatic recovery remains capped at two attempts per stage and separated by the existing cooldown.
- Alert delivery must be best-effort and must not hide or change the recovery exit status.
- All state writes must be atomic JSON writes.

---

### Task 1: Add a durable recovery heartbeat and run summary

**Files:**
- Modify: `src/ops_common/scheduled_recovery.py`
- Test: `tests/test_scheduled_recovery.py`

- [ ] Write a failing test asserting that a reconciliation writes `heartbeat.json` with `started_at`, `finished_at`, `success`, and stage counts.
- [ ] Run the focused test and verify it fails because the heartbeat is absent.
- [ ] Add atomic heartbeat writes at run start and completion, preserving the final receipt even when reconciliation raises.
- [ ] Run the focused test and the existing scheduled-recovery tests.

### Task 2: Add transition-aware failure notification

**Files:**
- Modify: `src/ops_common/scheduled_recovery.py`
- Modify: `scripts/systemd/market-intel-scheduled-recovery.service`
- Test: `tests/test_scheduled_recovery.py`

- [ ] Write a failing test asserting that a failed run emits one alert payload when the previous run was successful, and does not emit another identical alert on the next unchanged failure.
- [ ] Run the focused test and verify it fails because recovery has no notifier.
- [ ] Implement best-effort notifier injection for tests and a production notifier using the configured Feishu alert chat and lark-cli; record alert state in the recovery receipt.
- [ ] Add `--notify` to the recovery service command and load `.env.local` through the rendered unit environment.
- [ ] Run the focused test and all scheduled-recovery tests.

### Task 3: Validate installation and operational behavior

**Files:**
- Modify: `docs/daily-schedule.md`
- Test: `tests/test_scheduled_recovery.py`

- [ ] Add tests for the service template and heartbeat path.
- [ ] Run the full relevant pytest subset and shell syntax checks.
- [ ] Reinstall the recovery unit with `scripts/setup_cron.sh --recovery`.
- [ ] Run one audit-only recovery check and verify the heartbeat and receipt contain the expected stage summary.

