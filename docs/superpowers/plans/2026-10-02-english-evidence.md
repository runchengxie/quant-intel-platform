# English Evidence Repair Implementation Plan

> For agentic workers: use superpowers:executing-plans task-by-task. Validation artifacts and the progress ledger live in the user's external data directory.

**Goal:** Repair currency/evidence integrity and restore English homepage parity.

**Architecture:** Keep canonical JSON unchanged. Use the existing locale catalog for presentation, translate complete reviewed paragraphs before SVG wrapping, and reuse the existing image download implementation.

**Tech Stack:** TypeScript, Astro, Node test runner, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-02-english-evidence.md`.

## Global Constraints

- No source-data refresh, automated claim approval, delivery, credential change or runtime repin.
- English additions use locale catalogs, explicit time zones and unchanged fact magnitudes.
- No new dependencies or suppression of quality gates.

## Review Focus

- Explicit USD amounts and unqualified hundred-million ranges must never acquire CNY.
- Unknown future research paragraphs must retain source text, dates and URLs.
- Wrapped English paragraphs must not revert to partially translated fragments.
- Claim-only or duplicate source URLs must remain accessible without unsafe protocols.
- English PNG controls must target the displayed SVG and preserve report identity.

### Task 1: Faithful English currency and reviewed research

**Files:** `web/src/lib/locale.ts`, `web/src/lib/english-content.ts`, `web/src/lib/market-daily-utils.ts`, `web/tests/english-content.test.cjs`, `web/tests/market-daily-utils.test.cjs`.

**Interfaces:** Consume existing locale pairs and `toEnglishPresentation(string)`. Extend `buildMarketDailyChartSvg(summary, translate?, locale?)` with identity/Chinese defaults. Research claims use exact `usResearchText(source, locale)` lookup and bypass generic fragment translation. No data-contract changes.

- [x] Write failing tests for USD/CNY/unqualified units and the complete reviewed company paragraph translated before wrapping.
- [x] Run the targeted Node tests and verify genuine currency/pre-wrap failures.
- [x] Add currency-aware terms, exact source-bound locale paragraphs and the pre-wrap translation callback.
- [x] Run `npm test`; all 116 tests pass. Tasks 1 and 2 are committed together because the renderer and homepage integration form one evidence repair.

### Task 2: English evidence and homepage parity

**Files:** `web/src/pages/en/index.astro`, `web/src/lib/locale.ts`, `web/tests/astro-pages.test.cjs`, `web/browser-tests/public-site.spec.ts`, `web/docs/daily-generation-options.md`.

**Interfaces:** Consume Task 1's optional translation callback and existing `loadMarketDailyHistory`, `publicReportIdentity`, and `downloadMarketChartPng`.

- [x] Write built-page failing tests for all reviewed source URLs, report timestamps, PNG identity/targets and recent U.S. history. Add an English PNG browser check.
- [x] Run targeted build tests and verify missing-link/control failures.
- [x] Restore links, generation-time presentation, download controls and history using existing helpers. Date-scope the obsolete missing-chart statement.
- [x] Run all Node/web/root gates and browser checks: 981 root tests, 240 web Python tests, 116 Node tests and 10 browser tests pass. Web combined coverage is 86.48%; public fact artifacts are unchanged.
- [ ] Obtain independent branch review, merge after required checks, verify live Pages and clean only this task's resources.
