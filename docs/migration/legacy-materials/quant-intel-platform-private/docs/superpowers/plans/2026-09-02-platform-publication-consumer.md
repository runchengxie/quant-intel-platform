# Platform Publication Consumer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and resolve versioned research-platform publication bundles for market-intel report/distribution consumers.

**Architecture:** Reuse the canonical `research-contracts` manifest parser and add only market-intel-specific file resolution/hash verification. Preserve the existing no-source-import boundary.

**Tech Stack:** Python 3.11+, `research-contracts`, pathlib/json, pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-platform-publication-consumer-design.md`

## Global Constraints

- No research-workspace owner runtime import.
- No implicit sibling repository paths.
- Verify SHA-256 before returning projection paths.
- Public-only mode fails closed on internal artifacts.
- Merge requires a synchronized `uv.lock`.

---

### Task 1: Consumer behavior

**Files:**
- Create: `tests/test_platform_publication_consumer.py`
- Create: `src/ops_common/platform_publication.py`

- [x] Write tests for verified artifacts, internal disclosure mode, and tampering.
- [ ] Run the test and confirm RED before implementation.
- [x] Implement manifest loading, consumer filtering, safe path resolution, file checks, SHA-256 checks, and immutable receipts.
- [ ] Run `uv run pytest tests/test_platform_publication_consumer.py -q` after lock synchronization.

### Task 2: Upstream contract pin

**Files:**
- Modify: `pyproject.toml`
- Modify before merge: `uv.lock`

- [x] Temporarily pin `research-contracts` to the reviewed upstream feature commit.
- [ ] After workspace PR merge, replace the temporary pin with the merged `main` commit.
- [ ] Run `uv lock` and commit the generated lockfile. Do not hand-edit the lockfile.

### Task 3: Documentation and gates

**Files:**
- Create: `docs/platform-publication.md`

- [x] Document role, disclosure modes, and rollout order.
- [ ] Run `uv run python project_tools/check_all.py --scope all`.
- [ ] Run `uv run pytest`.
- [ ] Run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run ty check`.
