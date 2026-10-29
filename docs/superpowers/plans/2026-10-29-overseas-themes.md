# Overseas Theme Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Steps use checkbox syntax.

**Goal:** Distinguish overseas observations from retrospective research and current forecasts.
**Architecture:** Calendar-qualified quote aggregation and locale catalog rendering; explicit pinned research JSON input. Models stay in quant-market-research.
**Tech Stack:** Python, exchange-calendars, jsonschema, pytest, existing CLI.
**Spec:** ../specs/2026-10-29-overseas-themes-design.md

## Global Constraints
- No production deployment; preserve frozen forward-v1.
- No source imports from another owner; only versioned files.
- Missing evidence degrades visibly; no ETF recommendations without owner holdings evidence.
- Default English, explicit Chinese locale; timestamps interpreted in Asia/Shanghai.

## Review Focus
- Holidays and DST: only latest completed foreign exchange session contributes.
- NaN, booleans, missing dates and future observations: exclude from qualified averages.
- Legacy snapshots: mark unverified rather than elevate old bullish labels.
- Tampered, future or mismatched research files: reject with visible degradation.
- Negative study results and intervals crossing zero: display without promotion.

### Task 1: Qualified observations
**Files:** global_leadlag.py, cross_market.py, cross_market_index_receipt.py; tests/test_global_leadlag.py.
**Interfaces:** aggregate_concept_signals(quotes, mapping_table=None, *, decision_at=None) -> list[dict]; report_observation_context(date_text, generated) -> dict.
- [x] Add failing tests for nonfinite inputs, descriptive semantics and session eligibility; run pytest.
- [x] Implement versioned mapping metadata and calendar qualification without changing weights.
- [x] Wire production aggregation cutoff; run scoped tests and commit.

### Task 2: Reader presentation
**Files:** morning_report.py, cross_market_summary.py, report_messages.py, tests/test_morning_report.py.
**Interfaces:** consume qualified observations; render explicit observation-only copy and report stage.
- [x] Add failing tests for legacy bullish labels and report stages.
- [x] Implement localized observations and provenance; remove prediction-like tags.
- [x] Run morning/summary/locale/parity tests; retain representative synthetic reports outside source.

### Task 3: Research file consumer
**Files:** research_contracts/overseas_theme.py, a_share_daily/overseas_theme_report.py, cli.py, morning_report.py, versioned schema, contract tests and docs.
**Interfaces:** load_evidence(path, expected_sha256, observed_at) -> dict; render_morning_report(manifest, ...) -> str; manifest.overseas_theme_evidence holds path + sha256. CLI --overseas-theme-evidence and --overseas-theme-sha256.
- [x] Add failing schema/hash/time/source tests against provider schema.
- [x] Implement bounded file validation and attach only validated evidence with provenance.
- [ ] Show sample, paired error improvement/interval and limitations; missing/invalid artifact visibly degrades.
- [x] Run daily-report tests and project_tools/check_all.py --scope all; inspect diff; commit.

### Task 4: Integration
- [x] Provider PR validated/merged before consumer PR; verify destination and current target.
- [x] Validate consumer against provider revision and shared contract fixture.
- [ ] Merge after required checks; clean only task-owned resources and report exact results.


## Execution rulings

- The local manifest carries a pinned file pointer, rather than adding multiple renderer parameters;
  this preserves the existing report API and complexity gate while validation stays mandatory.
- The report cutoff uses the generation date; source data dates remain provenance. Naive explicit
  legacy timestamps mean Shanghai, while the implicit clock is timezone-aware. UTC-host regression
  was observed failing before the fix.
- Morning quote selection accepts an explicit cutoff; general daily-close callers keep their prior
  semantics. Session helpers moved to cross_market_sessions.py to keep the existing file under the
  repository's 800-line maintainability budget.
- A pre-existing /tmp Git checkout causes outside-source path tests to reject default pytest scratch.
  Full validation uses this task's external project-data scratch; no shared checkout was removed.
- Provider f918f2832938743bd743021a7dfd89590e6af002 supplies the schema; no empirical study artifact
  is selected because reviewed theme history and its complete reviewed manifest are missing.

- Independent review fixes: default pipeline and report clocks now use aware times; malformed quote
  objects cannot abort the report; legacy-only maps cannot assert checked provenance. All have
  observed red-to-green regressions. Missing research warnings have consistent markers in both locales.
- Cross-owner synthetic acceptance: provider f918f283 exported artifact SHA-256
  3a4488ee4a129f34fc87c48ec1e48e4663d860f73525eaa74f52b4ef6196d50c accepted by consumer; both locales
  retain negative gain -0.1, CI [-0.3, 0.05] and source links. Examples are explicitly synthetic and
  retained only in project task data, never promoted as market research.
- Provider PR #241 merged as 5122f1abd54bc69037631a4d45f8e28c24a29647; its three applicable CI jobs passed.

- Local complete gate: 1,656 tests passed, 71.11% total coverage, package coverage/type/lint/format/
  complexity and shell syntax gates passed. Local shellcheck/shfmt tools were absent and skipped;
  no shell source changed. Final pipeline-clock and SMH-label regressions were then added and
  the affected pipeline/observation/locale suites passed (34 and 56 tests respectively). Remote
  full-gate checks validate the eventual complete commit, including these final regressions.
- English/Chinese documentation build and public boundary check passed. No production deployment,
  production scheduler change or shared publication pointer update was performed.
