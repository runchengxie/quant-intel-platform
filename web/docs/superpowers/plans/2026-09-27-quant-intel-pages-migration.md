# Quant Intel Pages Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the public Pages project to `quant-intel-pages`, move its local checkout under `quant/`, and organize website code, public snapshots, and configuration samples without changing report content or publication rules.

**Architecture:** Keep Astro at repository root with application code in `src/`. Store Git-tracked public inputs under `artifacts/public/`, but emit the same `/data/` and `/reports/` browser paths. Update the separate deployment repository before an ordered GitHub/production cutover.

**Tech Stack:** Python 3.11, Astro 7, Node 22+, GitHub Actions/Pages, GitHub CLI, systemd user services.

**Spec:** `docs/superpowers/specs/2026-09-27-quant-intel-pages-migration-design.md`

## Global Constraints

- New repository: `runchengxie/quant-intel-pages`; new Pages base: `/quant-intel-pages/`. The old project URL may stop working.
- Public browser asset paths stay `/data/…` and `/reports/…`; report `source_url` values stay `reports/<id>.md` and schema IDs stay `market_intel_pages.*`.
- Only the five-date, reviewed public snapshot is tracked under `artifacts/public/`. Private candidate data, full archive, credentials, logs, and site build output stay outside Git.
- `configs/.env.example` contains blank sample values only. Runtime config comes from explicit environment variables or an external environment file; no hard-coded username.
- Never edit shared `main`, force-push, bypass hooks, delete unrelated worktrees, or make production depend on a task worktree. Pages and deploy require distinct branches and PRs; provider merges before consumer.
- Production release and scheduler configuration changes require separate authorization and rollback verification under `quant-intel-deploy/AGENTS.md`.

## Review Focus

- A malicious `source_url` such as `reports/../secret.md` must fail before reading either the public snapshot or the archive. Covered in Task 1's public-path test and existing archive-path validation test.
- A syntactically valid but unreviewed chart must not appear in the built Pages artifact after the path move. Covered in Task 2.
- A missing public Markdown or market-daily format must fail the build without replacing the prior site output. Covered in Task 2.
- A new Pages base must not leak `/market-intel-pages/` links into built HTML or chart fetch URLs. Covered in Task 3.
- A publisher configured with the old repository or URL must not silently claim a successful new-site publication. Covered in Task 4.

---

### Task 1: Public source-path boundary

**Files:**
- Create: `scripts/public_paths.py`
- Modify: `scripts/import_reports.py`, `scripts/import_charts.py`, `scripts/import_market_daily_report.py`, `scripts/sync_public_snapshot.py`
- Move: `data/**` → `artifacts/public/data/**`; `reports/**` → `artifacts/public/reports/**`
- Test: `tests/test_pipeline.py`, `tests/test_import_charts.py`, `tests/test_import_market_daily_report.py`, `tests/test_quality_paths.py`

**Interfaces:**
- Produces `public_snapshot_root(repo_root: Path) -> Path` returning `repo_root / "artifacts/public"`.
- Produces `safe_public_report_path(repo_root: Path, source_url: str) -> Path`, validating the unchanged `reports/<id>.md` public path before mapping it under the public snapshot root.
- Private archive paths remain under the existing external `archive_dir / data|reports`; never map archive files through `public_snapshot_root`.

- [ ] **Step 1: Write failing tests.** Assert imports write only under `artifacts/public/`, five-date pruning preserves the full external archive, and `safe_public_report_path(root, "reports/../secret.md")` raises `ValueError`.
- [ ] **Step 2: Run the focused tests.** `python3 -m pytest -q tests/test_pipeline.py tests/test_import_charts.py tests/test_import_market_daily_report.py tests/test_quality_paths.py`; expect failures on old paths or missing helper.
- [ ] **Step 3: Implement the path helper and migrate only repository-source reads/writes.** Keep URL fields and external archive paths unchanged; move tracked files with Git-aware staging.
- [ ] **Step 4: Rerun the focused tests.** Same command; expect PASS with no private path inside the repository.
- [ ] **Step 5: Commit the path boundary and snapshot move.** Review `git diff --cached --stat` for accidental archive or credential files first.

### Task 2: Build and Astro data flow

**Files:**
- Modify: `scripts/build_site.py`, `scripts/audit_chart_artifact.py`, `src/lib/reports.mjs`
- Test: `tests/test_build_site.py`, `tests/astro-pages.test.cjs`, `tests/reports-history.test.cjs`

**Interfaces:**
- Consumes Task 1's `public_snapshot_root` and `safe_public_report_path` for checkout inputs.
- Produces the existing static output contract: `output/data/**`, `output/reports/**`, Astro `output/index.html` and `output/reports/<id>/index.html`.
- `ASTRO_DATA_ROOT` continues to point to the staged output root; direct `npm run build` reads the checkout's `artifacts/public/` by default.

- [ ] **Step 1: Write failing tests.** Assert a real fixture builds from `artifacts/public/` into unchanged browser paths; an unreviewed chart is absent; a missing declared Markdown/TXT file raises before replacing prior output; direct Astro build reads the moved snapshot.
- [ ] **Step 2: Run the focused tests.** `python3 -m pytest -q tests/test_build_site.py && node --test tests/astro-pages.test.cjs tests/reports-history.test.cjs`; expect failure on old input paths.
- [ ] **Step 3: Update repository input paths and Astro's default data root.** Do not rewrite output-root or external-archive paths, which intentionally remain `data/` and `reports/`.
- [ ] **Step 4: Rerun focused tests and an isolated build.** Use an output directory outside the repo; expect unchanged public filenames and no unpublished chart data.
- [ ] **Step 5: Commit build-path changes.**

### Task 3: Source layout, configuration sample, and new site base

**Files:**
- Move: `index.html`, `app.js`, `styles.css`, `summary-utils.js`, `report-markdown.js`, `theme-utils.js` → `src/legacy/`; `market-daily-utils.js` → `src/lib/`; `.env.example` → `configs/.env.example`
- Modify: `src/pages/index.astro`, `src/lib/chart-data.mjs`, `astro.config.mjs`, `scripts/build_site.py`, `.github/workflows/deploy-pages.yml`, `package.json`, `package-lock.json`, `pyproject.toml`, `README.md`, `AGENTS.md`
- Test: `tests/*.cjs`, `tests/test_build_site.py`

**Interfaces:**
- Legacy fallback is published only at `/legacy/` with relative assets; Astro owns `/`.
- New Astro base is `/quant-intel-pages`; test fixtures must expect this path.
- The blank environment template is discoverable at `configs/.env.example`; runtime variable names do not change.

- [ ] **Step 1: Write failing Node/Python tests.** Assert new base in built links/chart fetches, zero old-base references in built HTML, functional `/legacy/index.html` assets, and `configs/.env.example` with no populated keys.
- [ ] **Step 2: Run focused tests.** `node --test tests/*.cjs && python3 -m pytest -q tests/test_build_site.py`; expect failures on old paths/base.
- [ ] **Step 3: Move sources and update imports, legacy copy rules, checks, workflow paths, package names, and current-use documentation.** Preserve historical dated design records rather than rewriting their history.
- [ ] **Step 4: Run full Pages repository gates.** Follow `AGENTS.md`: Ruff, ty, vulture, Python/Node tests, `node --check` at moved paths, isolated `build_site.py`, `npm run build`, `npm run check`, `pip-audit --strict`, structure audit, `git diff --check`; inspect generated HTML and legacy page links.
- [ ] **Step 5: Commit, push a Pages task branch, open a PR targeting user-owned `main`, obtain review/checks, and merge.** Keep the pre-migration production checkout unchanged until cutover.

### Task 4: Deployment consumer adaptation

**Files:**
- Modify in a separate `quant-intel-deploy` worktree: `config/market-pages-publisher.example.env`, `config/us-daily-pages-publisher.example.env`, `smoke_tests/test_market_pages_publisher.py`, and any current runbook section naming the repository or URL.
- Test: `smoke_tests/test_market_pages_publisher.py`

**Interfaces:**
- `MARKET_PAGES_REPOSITORY=runchengxie/quant-intel-pages`; `MARKET_PAGES_URL=https://runchengxie.github.io/quant-intel-pages/`.
- Stable `MARKET_PAGES_ROOT` and publisher checkout remain explicit external paths; no dependency on `.worktrees/`.

- [ ] **Step 1: Fetch deploy `origin/main`, inspect its status/worktrees/hooks, then create its own task branch and worktree.** Do not alter production config yet.
- [ ] **Step 2: Add a failing smoke test.** Assert new repo/URL configuration is used for PR creation and live-site verification, while an old URL cannot satisfy the new deployment check.
- [ ] **Step 3: Run the focused smoke test.** `uv run python -m pytest -q smoke_tests/test_market_pages_publisher.py`; expect FAIL on the old example values.
- [ ] **Step 4: Update example config and publisher/runbook only where tests demonstrate a real dependency.** Keep runtime environment externally configured.
- [ ] **Step 5: Run deploy `AGENTS.md` local gates, commit, push, open a separate PR, review, and merge after the Pages provider PR.** Do not bypass hooks or trigger routine remote Actions.

### Task 5: Ordered rename, local move, and production cutover

**Files:**
- Change GitHub repository name through `gh` after verifying admin access and merged provider/consumer commits.
- Update remote URL and main checkout directory only after confirming it is clean and no linked worktree is still in use.
- Update the external production environment file and stable release only with explicit production authorization.

**Interfaces:**
- Canonical Git remote becomes `runchengxie/quant-intel-pages`.
- Main local checkout becomes `/home/richard/code/quant/quant-intel-pages`; clean this task's linked worktrees after proving their PRs merged and before moving the main checkout.
- New live site is `https://runchengxie.github.io/quant-intel-pages/`.

- [ ] **Step 1: Record old repository/site state, publisher timer state, clean checkouts, rollback release, and current production env key names without exposing values.** If production authorization is absent, stop before modifying production or renaming the live repo.
- [ ] **Step 2: During the authorized cutover window, stop only the affected Pages publisher timer, rename the GitHub repository, and update canonical remotes.** Do not re-use the old GitHub repository name for a redirect repository.
- [ ] **Step 3: Publish from merged `main` and verify new home, dated report, Markdown/TXT, chart/data URLs, theme, mobile layout, and GitHub Pages workflow status.** A repository redirect is not evidence of a Pages redirect.
- [ ] **Step 4: Update production env/release with rollback ready, check publisher target, resume the affected timer, then observe a safe publication dry-run or next eligible batch.** Do not send Feishu messages; distinguish dry-run from a real scheduled publication.
- [ ] **Step 5: If checks fail, restore the previous production release/config and report exact failure. If checks pass, clean only this task's merged branches/worktrees in the AGENTS-prescribed order, move the now-unlinked clean main checkout under `quant/`, and record both PRs, merge SHAs, live URL, timer state, and any unobserved next-batch verification.** If someone else's linked worktree exists, defer the main-checkout move and report why.
