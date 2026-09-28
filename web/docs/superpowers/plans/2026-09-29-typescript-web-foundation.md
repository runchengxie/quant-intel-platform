# Quant Intel Web TypeScript Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or **superpowers:executing-plans** to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a strict TypeScript foundation for the public Astro site and migrate the chart data path without changing public URLs, runtime validation, or rendered behavior.

**Architecture:** Add Astro's strict TypeScript configuration, then migrate the small chart source and chart option modules to `.ts` and the React chart island to `.tsx`. JSON remains untrusted at runtime: loaders keep their existing identity checks, and TypeScript types describe the validated objects consumed after those checks.

**Tech Stack:** Astro 7, React 19, TypeScript, ECharts 6, Node test runner, npm.

**Spec:** The user supplied the 2026-09-28 technology adoption recommendation in the conversation: Python remains the data and artifact producer; TypeScript owns Web contract consumption and UI; runtime validation remains mandatory.

## Global Constraints

- Keep browser paths, artifact field names, error messages, and public report behavior unchanged.
- Do not add Java, Go, or Rust to `quant-intel-platform`.
- Do not replace runtime JSON validation with TypeScript assertions or casts.
- Keep existing CommonJS Node tests working while source modules move to `.ts`/`.tsx`.
- Do not edit the unrelated Pages path migration plan or any production/deploy configuration.

## Review Focus

- Invalid report IDs must still be rejected before a fetch; covered by the chart loader test.
- A non-public or mismatched chart payload must still be rejected after fetch; covered by a new loader test.
- Tooltip escaping and signed numeric formatting must remain unchanged; covered by the existing chart option test.
- React island cleanup must dispose the chart and observer on collapse/unmount; covered by the existing Astro build/type check and a focused component type surface.
- Source labels must remain stable for unknown and known HTTPS providers; covered by the existing market source tests.

---

### Task 1: Add strict Astro TypeScript foundation

**Files:**
- Create: `web/tsconfig.json`
- Modify: `web/package.json`, `web/package-lock.json`
- Test: `web/tsconfig.json` through `npm run check`

**Interfaces:**
- Produces Astro's strict project configuration with `allowJs: true` so unmigrated site modules remain usable during the incremental conversion.
- Keeps `npm run check` as the required type gate for `.astro`, `.ts`, `.tsx`, and existing JavaScript files.

- [ ] **Step 1: Add the type check command and strict config.** Use Astro's recommended `extends: "astro/tsconfigs/strict"`, enable `allowJs`, and keep `noEmit` enabled. Add only the TypeScript dependency/configuration required by Astro check.
- [ ] **Step 2: Run `npm run check`.** Expected: the current codebase is type checked and any real existing errors are reported before module migration.
- [ ] **Step 3: Fix only configuration or declaration issues exposed by the new gate.** Do not change runtime behavior or suppress errors with `any`/`@ts-ignore`.
- [ ] **Step 4: Rerun `npm run check` and commit.** Expected: PASS.

### Task 2: Migrate chart data and source labels to TypeScript

**Files:**
- Move: `web/src/lib/market-sources.mjs` → `web/src/lib/market-sources.ts`
- Move: `web/src/lib/chart-data.mjs` → `web/src/lib/chart-data.ts`
- Modify: `web/src/components/ChartIsland.jsx`, `web/tests/chart-data.test.cjs`, `web/tests/market-sources.test.cjs`
- Test: `web/tests/chart-data.test.cjs`, `web/tests/market-sources.test.cjs`

**Interfaces:**
- `factSource(fact: FactLike): FactSource | null` and `uniqueFactSources(facts: FactLike[]): FactSource[]` preserve their existing output.
- `loadChart(reportId: string, fetcher?: typeof fetch): Promise<ChartPayload>` preserves the existing identity validation and URL.
- `toOption(card: ChartCard): EChartsOption` preserves the current tooltip, zero line, units, colors, and signed display.

- [ ] **Step 1: Extend the chart loader test for a non-public payload and write the TypeScript-facing import expectation.** Keep the test behavior focused on rejection of an untrusted payload.
- [ ] **Step 2: Run `node --test tests/chart-data.test.cjs tests/market-sources.test.cjs`.** Expected: the new rejection case fails against the current test fixture or import surface, establishing the migration target.
- [ ] **Step 3: Rename the modules to `.ts`, define narrow input/output types, and preserve all runtime checks.** `response.json()` must be validated by the existing publication/report/chart checks before returning `ChartPayload`; no `as` cast may bypass that boundary.
- [ ] **Step 4: Update imports and rerun the focused Node tests.** Expected: PASS with the same URL, source labels, tooltip output, and rejection behavior.
- [ ] **Step 5: Run `npm run check` and commit.** Expected: PASS with the migrated modules included in Astro's type graph.

### Task 3: Migrate the React chart island to TSX

**Files:**
- Move: `web/src/components/ChartIsland.jsx` → `web/src/components/ChartIsland.tsx`
- Modify: `web/src/components/ChartCards.astro`
- Test: `web/tests/astro-pages.test.cjs`, `web/tests/chart-data.test.cjs`

**Interfaces:**
- `ChartIsland` accepts `{ reportId: string; chartKey: string }` and keeps the existing client-visible behavior.
- The dynamic chart engine import remains runtime-loaded only after expansion; chart disposal and `ResizeObserver` cleanup remain unchanged.

- [ ] **Step 1: Update the Astro component import and add a test assertion for the `.tsx` island path.** Keep the rendered page contract unchanged.
- [ ] **Step 2: Run `node --test tests/astro-pages.test.cjs`.** Expected: FAIL because the component still has the old `.jsx` path.
- [ ] **Step 3: Rename the component to `.tsx`, type its props, refs, chart instance, and cleanup handles, and update the Astro import.** Avoid changing user-visible copy or chart lifecycle behavior.
- [ ] **Step 4: Run the focused Node tests, `npm run check`, and `npm run build`.** Expected: PASS; build output contains the same public chart routes and no old module import.
- [ ] **Step 5: Commit the TSX migration and update the plan status.**

### Completion

- [ ] Run the Web checks required by `web/AGENTS.md` that are available locally: `npm run check`, `npm run build`, the focused Node tests, and `git diff --check`.
- [ ] Record any unavailable Python or dependency audit checks without claiming them as passing.
- [ ] Push the task branch and open a PR targeting `main`; do not merge or change production configuration in this task.
