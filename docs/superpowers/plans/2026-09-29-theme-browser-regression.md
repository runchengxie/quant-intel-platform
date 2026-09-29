# Theme and Browser Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make downloaded report PNGs match the active light/dark theme and prevent navigation or report graphics regressions at desktop and mobile widths.

**Architecture:** Inline the displayed SVG's resolved theme variables into a clone before PNG rasterization. Add a compact Playwright Chromium suite against the built Astro site for real layout/color checks. Because the current root redirects to English, cover the English entry and the Chinese report view (`/?locale=zh-CN`), including a matching English theme toggle.

**Tech Stack:** Astro 7, TypeScript, Node `tsx --test`, `@playwright/test` 1.63.0 with Chromium, existing GitHub `Public website` workflow.

**Spec:** `docs/superpowers/specs/2026-09-29-public-site-reliability-design.md`

## Global Constraints

- Keep the original report SVG untouched; export a themed clone. Preserve file names, scaling limits, PNG errors and object-URL cleanup.
- Use current `--report-bg`, `--report-ink`, `--report-muted`, `--report-track`, `--report-line` values; fall back to existing light colors only when computed theme values are unavailable.
- Run browser checks against the built public sample site, with no private data, network market calls or full-page golden screenshots.
- Cover 390, 768 and 1280 px widths and both light/dark states. Do not silently skip a missing chart; assert expected report elements exist.
- PR checks must build and test only; Pages deploys only after merge to `main`.

## Review Focus

- `getComputedStyle` unavailable or a blank custom property must not produce a blank/transparent PNG (Task 1).
- Image load or blocked download failure must still revoke the source URL and remove any appended anchor (Task 1).
- Local storage denied or OS theme changed must leave theme button usable and `aria-pressed` truthful (Task 2).
- A narrow viewport with the optional history link must not overlap the theme button or hide navigation access (Task 3).
- A chart missing from public sample data must make the browser test fail clearly, not vacuously pass (Task 3).

---

### Task 1: Serialize the displayed SVG theme into PNG export

**Files:**
- Modify: `web/src/lib/market-chart-download.ts`
- Modify: `web/tests/market-chart-download.test.cjs`

**Interfaces:**
- Preserve: `downloadMarketChartPng(svg: SVGElement, date: string, kind: 'market-daily' | 'asia-daily' = 'market-daily'): Promise<void>`.
- Internal helper: `serializeSvgWithResolvedTheme(svg: SVGElement): string`; it clones `svg`, copies five nonempty computed CSS variables to the clone's inline style, and serializes the clone.

- [ ] **Step 1: Add failing tests** to `web/tests/market-chart-download.test.cjs`: fake a dark computed style, capture the first `Blob` and assert its SVG markup includes dark background/text variables; assert original SVG style is unchanged and blank values retain light fallbacks. Extend the existing load/click-failure tests to assert URL cleanup after the clone path.
- [ ] **Step 2: Run `cd web && node --import tsx --test tests/market-chart-download.test.cjs`**; expect the new theme serialization assertion to fail because the blob still contains unresolved `var(...)` only.
- [ ] **Step 3: Implement the internal helper** in `web/src/lib/market-chart-download.ts`; use `svg.cloneNode(true)`, `getComputedStyle(svg).getPropertyValue(name).trim()`, and `style.setProperty` only for valid nonempty values; never edit the live SVG.
- [ ] **Step 4: Run the focused command and `cd web && npm test`**; expect all tests green. Run `cd web && npm run build` to catch TypeScript/Astro bundling errors.
- [ ] **Step 5: Commit** the two files as `fix: preserve report theme in PNG downloads`.

### Task 2: Theme parity on the English default entry

**Files:**
- Modify: `web/src/pages/en/index.astro`
- Modify: `web/tests/astro-pages.test.cjs`
- Modify: `web/src/styles/site.css` only if the real browser check shows a gap/layout defect.

**Interfaces:**
- Reuse: storage key `market-intel-theme`, root `data-theme` attribute, `aria-pressed`, and the existing `theme-toggle` button ID/labels. English button text is `Dark mode`; its accessible label changes between `Switch to dark mode` and `Switch to light mode`.
- The Chinese route remains `/?locale=zh-CN`; root `/` continues redirecting to `/en/` as current `main` specifies.

- [ ] **Step 1: Add failing source/build tests** in `web/tests/astro-pages.test.cjs` proving the English entry has a button, the same storage key, pre-paint theme initialization, and toggle behavior under a denied-storage fake. Keep existing Chinese assertions intact.
- [ ] **Step 2: Run `cd web && node --import tsx --test tests/astro-pages.test.cjs`**; expect failure because the English page has no theme control.
- [ ] **Step 3: Add the button and theme bootstrap/controller** to `web/src/pages/en/index.astro`, following the existing Chinese page's small script rather than refactoring unrelated report behavior. Keep both pages' `aria-pressed` synchronized with `data-theme`.
- [ ] **Step 4: Re-run focused test, `cd web && npm test`, and `cd web && npm run build`**; expect zero failures. Do not infer visual layout correctness from these unit tests; Task 3 measures it in Chromium.
- [ ] **Step 5: Commit** as `feat: support theme switch on English entry`.

### Task 3: Real-browser layout, theme and PNG smoke checks

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/browser-tests/public-site.spec.ts`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/src/styles/research-language.css` if the 768 px navigation test fails.
- Modify: `web/src/styles/site.css` if the English entry needs responsive adjustment.
- Modify: `.github/workflows/public-site.yml`
- Modify: `docs/how-to/market-site.md`

**Interfaces:**
- Produces: `npm run test:browser` from `web/`, which builds the public sample Astro site and runs Playwright Chromium against `astro preview` on localhost. Tests must route explicitly to `/quant-intel-platform/en/` and `/quant-intel-platform/?locale=zh-CN`.
- The CI build job installs a pinned Playwright package/browser, invokes `npm run test:browser`, and uploads trace/screenshot artifacts only on failure.

- [ ] **Step 1: Add `@playwright/test@1.63.0` and config**, using one worker in CI and `trace: 'on-first-retry'`; then write browser tests for 390/768/1280 px: English and Chinese header link/button rectangles do not intersect; Chinese navigation remains reachable; theme switch + reload preserves `data-theme` and SVG computed background/text colors; a missing report/chart fails explicitly; downloaded PNG's top-left background pixel matches the displayed SVG background. Add one historical evening-report URL load/color smoke test without a full-page pixel snapshot.
- [ ] **Step 2: Run `cd web && npm run test:browser`**; record each expected red failure before changing production CSS (notably the newly measured 768 px layout or PNG behavior). Browser setup errors are not acceptable red tests; install Chromium first if needed.
- [ ] **Step 3: Make only measured CSS corrections** in `research-language.css`/`site.css`; use wrapping or an earlier responsive breakpoint if the 768 px header overflows, keeping the theme button reachable and nav links at least 12 px apart. Do not weaken browser assertions to make red pass.
- [ ] **Step 4: Re-run browser tests, `cd web && npm test`, `cd web && npm run check`, `cd web && npm run build`, `uv run python project_tools/check_all.py --scope all`, and `uv run mkdocs build --strict`**; record exact successes/failures and any resource limit. Add the browser command and CI artifact behavior to the market-site runbook.
- [ ] **Step 5: Wire `test:browser` into `.github/workflows/public-site.yml`** after `npm ci`; install the browser with `npx playwright install --with-deps chromium`, run the suite, and upload trace/screenshot artifacts on failure. Re-run `git diff --check` and the browser suite before committing as `test: gate public site layout and theme in Chromium`.
- [ ] **Step 6: Push and open a PR** to the user's `main`. Merge only after required checks/review pass; verify the post-merge Pages run and the live English/Chinese entry points.
