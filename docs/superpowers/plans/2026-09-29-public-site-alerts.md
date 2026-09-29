# Public Site Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alert maintainers on failed public-site publication checks and on public U.S./Asia reports older than 96 hours, without private credentials or production scheduler changes.

**Architecture:** A pure freshness evaluator reads the two public JSON contracts; a small GitHub Issue reconciler opens or closes one issue per alert key; a trusted default-branch workflow invokes them for scheduled and `workflow_run` events. No PR code or artifact is executed in the privileged workflow.

**Tech Stack:** Python 3.11+, pytest, GitHub Actions, GitHub REST API, existing `web/scripts/pipeline_health.py`.

**Spec:** `docs/superpowers/specs/2026-09-29-public-site-reliability-design.md`

## Global Constraints

- Use only public Pages JSON and `GITHUB_TOKEN`; do not add secrets, market scraping, model calls, Feishu, or private deploy changes.
- Recompute age when monitoring runs; do not trust the static `health.json` timestamp. Default warning threshold: 96 hours.
- A stale warning means human review is needed, not proof of a missed trading-day SLA. Never block Pages deployment on stale data.
- Only the alert job gets `issues: write`; do not execute PR code in `workflow_run`.
- Never post report content or raw HTTP error bodies to GitHub Issues.

## Review Focus

- Malformed, missing, oversized or non-JSON Pages response must become a bounded availability finding, without logging its body (Task 1).
- Naive/future timestamps or an invalid market date must not be classified as fresh (Task 1).
- A long market closure may trip 96-hour warning; wording must say “review freshness,” not “publication failed” (Task 1).
- Duplicate/delayed workflow events must not create repeated Issues or close an alert for a different branch (Task 2).
- A GitHub API error must leave the workflow red and must not falsely claim an alert was delivered (Task 2).

---

### Task 1: Runtime freshness evaluation

**Files:**
- Create: `web/scripts/public_site_freshness.py`
- Create: `web/tests/test_public_site_freshness.py`
- Modify: `docs/how-to/market-site.md`

**Interfaces:**
- Produces: `evaluate_public_snapshots(reports: dict, us_report: dict, *, now: datetime, max_age_hours: int = 96) -> list[dict[str, str]]`; each finding has `key`, `status`, `summary` and no report body.
- Produces: `fetch_public_snapshots(base_url: str, *, timeout_seconds: int = 10, max_bytes: int = 4_000_000) -> tuple[dict, dict]`; only two fixed `/data/*.json` URLs under the configured HTTPS Pages base.
- Consumes: `health_report` from `web/scripts/pipeline_health.py` for Asian report date/generation semantics.

- [ ] **Step 1: Write failing pytest cases** in `web/tests/test_public_site_freshness.py` for fresh Asian + U.S. reports, either side >96 hours, malformed/future/naive timestamps, missing rows, and bounded network/JSON failures; assert keys, non-sensitive summaries, and “review” wording for a simulated long closure, not implementation details.
- [ ] **Step 2: Run `cd web && python -m pytest tests/test_public_site_freshness.py -q`**; expected failure is missing module/functions, not test setup error.
- [ ] **Step 3: Implement the two signatures** in `web/scripts/public_site_freshness.py`; parse U.S. `run_id` (`daily-YYYY-MM-DD`) and `generated_at`, calculate both generated-at and market-date age with timezone-aware `now`, and reuse Asian `health_report`; use a fixed-size response read and a 10-second timeout.
- [ ] **Step 4: Re-run the focused pytest command** and then `cd web && python -m pytest -q`; expect zero failed tests. Update the market-site runbook with the 96-hour review limitation and the two live JSON URLs.
- [ ] **Step 5: Commit** the evaluator, tests and runbook as `feat: evaluate live public report freshness`.

### Task 2: Idempotent GitHub Issue reconciliation

**Files:**
- Create: `web/scripts/public_site_alerts.py`
- Create: `web/tests/test_public_site_alerts.py`

**Interfaces:**
- Consumes: Task 1 findings; a workflow failure is passed as a separate alert key `build:<branch>`.
- Produces: `reconcile_alert(client: IssueClient, *, key: str, finding: str | None, run_url: str, event_id: int) -> str`; `finding=None` closes only that key's open issue, and an event older than the issue's recorded `event_id` makes no change. `IssueClient` wraps the minimal GitHub REST list/create/comment/close calls with `GITHUB_TOKEN` and repository from the workflow environment.

- [ ] **Step 1: Write failing tests** for first failure creates one labeled Issue, repeated failure updates that Issue, recovery closes it, an unrelated branch remains open, an older event cannot reopen/close a newer state, and REST error propagates; use a fake Issue client, never the real GitHub API.
- [ ] **Step 2: Run `cd web && python -m pytest tests/test_public_site_alerts.py -q`**; expect missing implementation failure.
- [ ] **Step 3: Implement the typed Issue client and `reconcile_alert`** with fixed marker `[public-site-alert:<key>]`, last `event_id` and `public-site-alert` label; escape/encode API values, cap diagnostic text, and keep sensitive response bodies out of exception messages.
- [ ] **Step 4: Re-run focused and full web pytest**; expect zero failures. Run `ruff check scripts/public_site_alerts.py tests/test_public_site_alerts.py` and `ty check` from `web/`.
- [ ] **Step 5: Commit** as `feat: reconcile public site alert issues`.

### Task 3: Trusted Actions wiring and dry-run verification

**Files:**
- Create: `.github/workflows/public-site-monitor.yml`
- Modify: `web/scripts/public_site_alerts.py`
- Modify: `web/tests/test_public_site_alerts.py`
- Modify: `docs/how-to/market-site.md`

**Interfaces:**
- Consumes: Tasks 1–2 functions via CLI entry points `python web/scripts/public_site_alerts.py --mode freshness` and `--mode workflow`; the script reads the scheduled/workflow event JSON from `GITHUB_EVENT_PATH` and supports `--dry-run` for manual validation.
- Produces: one scheduled health check, and one `workflow_run` listener for completed `Public website` runs on `main` or `automation/pages-*`; all Issue writes are from the trusted default-branch checkout.

- [ ] **Step 1: Write failing tests** for event filtering (ignore unrelated branches/workflows), failed build alert, same-branch success closure, schedule stale/healthy reconciliation, and dry-run issuing no write calls; statically assert workflow job `issues: write` and `workflow_run` event.
- [ ] **Step 2: Run `cd web && python -m pytest tests/test_public_site_alerts.py -q`**; expect missing CLI/event behavior failure.
- [ ] **Step 3: Implement the CLI and workflow** with `0 */6 * * *` UTC scheduled checks and `workflow_dispatch` dry-run input; checkout default branch only, pass event fields through environment/file rather than interpolating PR strings in shell, use `workflow_run.id` or `GITHUB_RUN_ID` as `event_id`, set minimal permissions, and avoid uploading report bodies.
- [ ] **Step 4: Run focused tests, `cd web && python -m pytest -q`, `uv run python project_tools/check_all.py --scope all`, `uv run mkdocs build --strict`, and `git diff --check`**; record exact results, including any local resource limitation. Update runbook with GitHub notification subscription and manual trigger instructions.
- [ ] **Step 5: Commit** as `feat: monitor public site publication and freshness`; push only the owned task branch and open a PR targeting the user's `main`. Merge only after required checks/review and no conflicts; then verify a normal dry-run dispatch, without creating test Issues.
