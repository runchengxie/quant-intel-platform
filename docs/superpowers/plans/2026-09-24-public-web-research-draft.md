# Public-web Research Draft Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a private, dated, source-linked research draft for the six-section US market daily report.

**Architecture:** A focused CLI command calls Codex live search with a strict output schema, then validates candidate provenance and dates before writing an immutable draft and receipt. No draft is promoted into `daily_report.json` in this change.

**Tech Stack:** Python stdlib, existing `dm` CLI, Codex CLI, pytest, ruff, ty.

**Spec:** `docs/superpowers/specs/2026-09-24-public-web-research-draft-design.md`

## Global Constraints

- Output remains private and requires review; no automatic publication.
- The requested US trading date is distinct from publication time.
- Sources after the run cutoff, non-HTTP(S) URLs, and mismatched observation dates are rejected.
- Production tasks must use a stable release and external data directory.
- No keys or raw model output enter the repository or public Pages.

## Review Focus

- A previous-day article published on the target day must be rejected as target-day evidence.
- A pre-close article must not claim a final close; the prompt and draft type must make this reviewable.
- Timezone-less publication timestamps must be rejected.
- A partial or malformed Codex response must not replace an earlier usable draft.
- A search result snippet without a supporting passage must be rejected.

---

### Task 1: Draft parser and validation

**Files:** `src/daily_messenger/daily_report/web_research.py`, `tests/daily_report/test_web_research.py`.

**Interfaces:** `validate_candidates(payload: object, *, market_date: date, cutoff: datetime) -> tuple[list[dict[str, str]], list[str]]` returns candidates with `review_status=needs_review` and rejection reasons.

- [ ] Write tests for a valid candidate and each review-focus rejection using fixed 2026-09-18 and 2026-09-23 examples.
- [ ] Run `uv run pytest tests/daily_report/test_web_research.py -q`; verify feature-missing failures.
- [ ] Implement minimal validation with explicit fields and timezone-aware `datetime.fromisoformat`.
- [ ] Run the focused tests; verify green.

### Task 2: Codex invocation and artifact persistence

**Files:** `src/daily_messenger/daily_report/web_research.py`, `src/daily_messenger/cli.py`, `tests/daily_report/test_web_research.py`, `tests/daily_report/test_web_research_cli.py`.

**Interfaces:** `run_web_research(market_date: date, output_dir: Path, *, cutoff: datetime, codex_bin: str = "codex") -> Path` writes a unique JSON draft and raises a clear error on failure. `dm research` dispatches to it with required date/output arguments.

- [ ] Write failing tests for the command arguments, immutable output, nonzero exit, malformed JSON, and CLI dispatch.
- [ ] Run focused tests; verify feature-missing failures.
- [ ] Add the strict schema and prompt in the module; invoke `codex --search exec --sandbox read-only --output-schema ... --output-last-message ...` with timeout.
- [ ] Validate, then atomically write the private artifact and receipt. Reject output paths within the checkout.
- [ ] Run focused and all daily-report tests; verify green.

### Task 3: Quality gate and live probe

**Files:** `docs/superpowers/specs/2026-09-24-public-web-research-draft-design.md`, this plan, production code and tests from Tasks 1–2.

- [ ] Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check`, `uv run pytest`, `uv run python project_tools/update_cli_help.py --check`, and `uv run python project_tools/check_all.py --scope all`.
- [ ] Run one manual `dm research` for a completed US trading date into an external private directory; inspect candidate count and rejection reasons without exposing copyrighted article text in logs.
- [ ] Review diff and status, commit, push, open a PR, and merge only after required checks and review requirements pass.
