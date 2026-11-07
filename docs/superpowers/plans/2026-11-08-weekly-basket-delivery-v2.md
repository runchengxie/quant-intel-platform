# Weekly Basket Delivery v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Prevent weekly basket duplicate sends and false success across restarts, historical receipts, and changed render output.

**Architecture:** Canonical week-scoped private state serializes delivery and durably checkpoints each transport phase. Immutable render bundles supply verified payloads. The CLI supplies stable roots and declared sender identity and emits redacted status projections.

**Tech Stack:** Python, pathlib, standard-library process locking and fsync, pytest, existing lark CLI transport.

**Spec:** [Approved specification](../specs/2026-11-08-weekly-basket-delivery-v2.md).

## Global Constraints

- Preserve provider idempotency keys and historical receipt bytes.
- Never automatically reopen inflight, uncertain, or legacy attempts.
- No production activation, real message sends, dependency additions, or quality exclusions.
- All task runtime output stays outside the source checkout.

## Review Focus

- Same-week requests with different dates must not open another provider slot.
- Concurrent processes must share a stable lock inode and send once.
- Malformed success JSON and crash windows must hold rather than retry.
- Image mutation after text acceptance must retain evidence and prevent substitution.
- Dry runs and public output must not modify live state or disclose routing identity.

### Task 1: Durable delivery state and transport

**Files:** `src/a_share_daily/weekly_client_basket_delivery.py`, focused delivery store modules, `tests/test_weekly_client_basket_delivery.py`, dedicated v2 tests.

**Interfaces:** Preserve existing send function names; add keyword arguments `sender_scope`, `delivery_state_root`, `legacy_receipt_root`, and `render_manifest_path`. Preserve receipt `status` and `image_status`; add verification/phase outcome fields and a redacted public projection.

- [x] Write and run failing tests for strict CLI acceptance, historical hold, changed-date/sender/content hold, missing configuration, durable checkpoints, image mutation, and process serialization.
- [x] Implement the canonical provider-target/week slot, stable process lock, durable atomic state, schema dispatch, and frozen payload checks.
- [x] Implement text/image phase transitions and compatibility receipt projections.
- [x] Run focused tests and inspect receipt permissions and unchanged historical bytes.
- [x] Commit after coordinated integration validation.

### Task 2: Immutable render bundles

**Files:** `src/a_share_daily/weekly_client_basket_render.py`, focused render bundle module if needed, renderer tests.

**Interfaces:** `write_rendered_outputs` retains `markdown`, `csv`, `png` Path keys pointing to an immutable bundle and adds a `manifest` Path. Manifest schema `weekly_basket.render.v1` contains report_date, artifact_sha256, and `files` entries with relative `path`, sha256, and size.

- [x] Write and run failing tests for complete manifest/hash agreement, immutable earlier bundles, private modes, and failed rendering not publishing a partial bundle.
- [x] Implement separate render locking, atomic bundle publication, and compatibility aliases.
- [x] Run renderer tests and coordinate manifest parsing with Task 1.
- [x] Commit after coordinated integration validation.

### Task 3: CLI integration and migration documentation

**Files:** `src/a_share_daily/weekly_basket_command.py`, `src/a_share_daily/weekly_basket_state.py` (read-only `load_weekly_lock`), `src/a_share_daily/cli.py`, CLI tests, generated CLI help, relevant operational docs.

**Interfaces:** `--sender-scope` / `WEEKLY_BASKET_SENDER_SCOPE`; delivery root is `state_root/delivery`, legacy root is output_root. Send exact rendered markdown bytes and manifest. Preview artifacts/new state use unique preview namespaces with a separate authoritative read root.

- [x] Add failing tests for missing sender configuration, preview isolation, redacted failure output, and required-phase aggregation.
- [x] Wire sender, stable roots, manifest, public projections, and non-vacuous aggregate success.
- [x] Document source-only migration and legacy hold; regenerate CLI help.
- [x] Run CLI/contract tests and full repository gates.

### Task 4: Review and delivery

- [x] Inspect combined diff and run `uv run python project_tools/check_all.py --scope all` with task-local external temporary and coverage paths.
- [x] Obtain independent whole-branch review and resolve findings with regression tests.
- [ ] Verify owner push destination, commit, push, open PR against owner main, and verify required checks against the final revision.
- [ ] Merge only after checks pass and current-main compatibility is established; verify merged SHA before cleaning only current task resources.
- [ ] Report source merge separately from production deployment and consumer adoption.
