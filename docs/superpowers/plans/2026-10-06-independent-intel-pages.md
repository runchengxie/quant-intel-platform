# Independent Quant Intel Pages Implementation Plan

> Steps use checkbox syntax for tracking. The user authorized implementation and the production cutover on 2026-10-06.

**Goal:** Restore independent daily-report frontend ownership and deployment in Pages while keeping production and evidence validation in Platform.

**Architecture:** Platform exposes an installed CLI that validates and exports a public website snapshot without building HTML. Pages consumes that snapshot through the CLI, builds Astro, and deploys its own website. Deploy publishes reviewed report artifacts to Pages using pinned Platform executables.

**Tech Stack:** Python 3.11+, Astro 7, React 19, Node 24, GitHub Pages, MkDocs, uv, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-independent-intel-pages-design.md`

## Global Constraints

- Preserve report schemas, evidence identifiers, timestamps, hashes, explicit public manifests, and private archives.
- Keep the five-date public report window and current locale behavior.
- Use installed public CLI or versioned files across repositories; no sibling source imports.
- Keep model generation, commentary prompts, acquisition, and backend implementation in Platform.
- Preserve historical Pages material after collision inventory; do not rewrite history.
- Use independent worktrees and PRs; complete required gates and merge providers before consumers.
- Actual private configuration, production releases, and scheduler changes require separate production authorization.

## Review Focus

- Invalid hashes, symlinks, or incomplete snapshots must fail before replacing a previously valid output (Task 1).
- Latest US report and history disagreement must prevent deployment; legacy accepted editions must remain readable (Task 1).
- Missing owner CLI or a failed Astro build must preserve existing site output (Task 2).
- Pending publication receipts from Platform must not count as proof of Pages publication (Task 3).
- Old report links with fragments or query parameters must reach the corresponding Pages route; `/docs/` remains available (Task 4).

## Task 1: Complete Platform publication interfaces

**Files:**
- Create: `src/market_intel_publication/export_site_snapshot.py`, `chart_contract.py`, `chart_review.py`, `import_charts.py`, `pipeline_health.py`.
- Modify: `pyproject.toml`, `project_tools/update_cli_help.py` if CLI inventory requires it.
- Move relevant backend tests from `web/tests/test_build_site.py`, `test_chart_contract.py`, `test_import_charts.py`, and commentary/publication wrapper tests to root `tests/`.
- Retain `web/` and its workflow until the final removal task.

**Interfaces:**
- Consumes: `artifacts/public/data/` and `artifacts/public/reports/` under explicit `--root`; existing publication and commentary contracts.
- Produces: `market-export-site-snapshot --root PATH --output PATH [--summaries PATH]`, `market-import-charts`, and `market-chart-review` installed entry points.
- Define `export_site_snapshot(root: Path, output: Path, summaries_path: Path | None = None) -> None`. Output includes validated `data/` and `reports/`, health, summaries, insights, public chart/news projections, and report download formats; it contains no frontend assets or HTML.
- Preserve existing chart command argument names and JSON results when moving their implementations.

- [x] Add `tests/test_export_site_snapshot.py` coverage for unchanged representative Asia/US output, five-date limit, invalid hash/unsafe path, latest/history mismatch, and output preservation after failure. Reuse existing fixtures and meaningful tests.
- [x] Run the focused tests and record failures before implementing the exporter.
- [x] Extract data validation/copying from `web/scripts/build_site.py`; keep atomic output replacement and reuse owner contract modules. Move chart validation/review/import and health implementation into the owner package, leaving temporary compatibility wrappers in `web/scripts/`.
- [x] Move backend tests out of website wrappers; update website tests to verify wrappers and frontend behavior without maintaining a second backend suite.
- [x] Run root contract tests, `uv run python project_tools/check_all.py --scope all`, and existing website checks to prove the additive change preserves current publication.
- [x] Commit, push, open and merge the Platform interface PR after local and required remote checks pass. Pin its merged SHA for subsequent tasks.

## Task 2: Restore Pages frontend and independent deployment

**Files:**
- Transfer maintained `web/src/`, `browser-tests/`, Node configs, `package.json`, and `package-lock.json` to Pages root.
- Modify: Pages `scripts/build_site.py`, `pyproject.toml`, `AGENTS.md`, both READMEs, relevant `docs/`, `.github/workflows/`.
- Transfer frontend Python/Node/browser tests and monitoring adapters; preserve frontend chart audit and static contract checks where required.
- Remove obsolete Pages backend generation implementations and prompts after replacement inventory; keep the archive lifecycle record and recoverable historical material.

**Interfaces:**
- Consumes: installed `market-export-site-snapshot`, pinned to the merged Task 1 commit in website CI; no Platform Python imports or sibling path configuration.
- Produces: `python scripts/build_site.py --output PATH`, static Pages site rooted at `/quant-intel-pages`, `public-site.yml` build job named `build`, and `market-intel-ledger-${run_id}-1` artifact containing the public data/report ledger.
- Retain `build_site(root: Path, output: Path, summaries_path: Path | None = None) -> None` for frontend tests, implemented as CLI export plus static asset copying and Astro rendering in staging.

- [x] Inventory tracked Pages archive files against maintained Platform website files; record the prior Pages and Platform immutable revisions and preserve archive-only artifacts outside the current public window.
- [x] Add/update build adapter tests: missing CLI and failed Astro preserve previous output; backend Python imports are absent; deployment workflow contains no model secrets or generation steps.
- [x] Transfer current frontend files and rendering tests; update Astro base, browser routes, monitoring URL, documentation links, and redirect behavior. Preserve locale catalogs and selections.
- [x] Replace the build implementation with CLI invocation and static frontend copying/rendering; install the pinned Platform package in CI as a CLI dependency. Keep Pages Python dependencies limited to its checks and frontend adapters.
- [x] Replace the old secret-consuming workflow with `public-site.yml`; adapt monitoring workflow paths and keep the publication ledger and `build` job contract compatible with Deploy.
- [x] Remove historical generation wrappers, model implementations/prompts, and their tests after locating the Task 1 owner equivalents. Update ownership and archive documentation.
- [x] Run required Pages lint/type/coverage/Node checks, dependency audit, Astro check/build, structural audit, and browser tests for representative Asia/US reports, locale selection, sources, and downloads. Keep temporary outputs outside repositories.
- [x] Commit, push, open and merge the Pages PR after required checks. Verify the website build and independently deployed Pages artifact; record merged SHA.

## Task 3: Adapt Deploy to Pages contracts

**Files:**
- Modify: `scripts/publish_market_pages.py`, `publish_us_daily_pages.py`, `market_pages_reviewed_charts.py`, `market_pages_automatic_review.py`, `market_pages_commentary.py`, `check_production_release.py` as required.
- Modify: `config/market-pages-publisher.example.env`, `config/us-daily-pages-publisher.example.env`, deployment manifests and active documentation referencing combined website paths.
- Modify: corresponding `tests/smoke/test_*pages*.py`, chart review and production preflight tests.
- Add: `docs/independent-pages-cutover.md`.

**Interfaces:**
- Consumes: merged Pages Task 2 workflow/ledger and root `artifacts/public/` layout; installed Platform chart/import/commentary CLI.
- Produces: report-only bot PRs to `runchengxie/quant-intel-pages`; publication success requires exact expected hashes and successful website workflow verification.
- `MARKET_PAGES_ROOT` selects the stable frontend release; owner interpreter/CLI settings select the distinct pinned Platform runtime. Keep Asia and US executable roles explicit in configuration examples.

- [x] Update fixtures/assertions for root artifact paths and Pages destination; test that backend source files and the other publisher's report paths remain outside each allowlist.
- [x] Test that pending receipts tied to a different repository cannot silently resume or declare success against Pages. Pin publisher state to its repository identity and fail with a recoverable diagnostic on mismatch.
- [x] Replace `web/artifacts/public` paths and `checkout / 'web'` roots in both publishers, chart expectations, URL verification, and ledger handling. Invoke owner-installed chart CLIs rather than frontend scripts.
- [x] Update example configuration and production preflight checks for separate owner/frontend releases. Keep workflow name `public-site.yml` and job name `build` consistent with Task 2.
- [x] Write the cutover runbook: inventory active jobs, bot branches, receipts, releases/aliases and downstream links; pause affected publishers; settle or preserve pending transactions; use new bot checkout/state roots for Pages; pin merged releases; perform no-send preflight; switch and resume; verify Asia/US routes and restore prior pins/configuration on failure.
- [x] Run all required Deploy local quality gates, smoke coverage, shell checks, audits, and `git diff --check`; do not trigger private Actions for routine validation.
- [x] Commit, push, open and merge Deploy PR; record merged pins and exact prepared production changes. Request production-switch authorization only after the result is reviewable.

## Task 4: Cut over production and retire Platform frontend

**Files:**
- Modify Platform: `.github/workflows/public-site.yml`, `mkdocs.yml`, documentation navigation, both READMEs, `AGENTS.md`, `pyproject.toml`, and public boundary checks.
- Move Platform calendar configuration out of `web/configs/` into owner `config/`; update `project_tools/export_public_asia_calendar.py` and `tests/test_public_asia_calendar.py`.
- Remove Platform `web/` and website monitor workflow after proving production and rollback no longer call them.
- Create Platform `project_tools/build_docs_site.py` and `tests/test_build_docs_site.py` for the docs-only artifact and report compatibility entry point.

**Interfaces:**
- Consumes: merged Task 1–3 commits and separately authorized production switch.
- Produces: stable publisher releases/configuration using Pages; Platform artifact with `/docs/` MkDocs content and root compatibility redirect to Pages, retaining query/hash.

- [x] Inventory production references read-only and present concrete configuration/pin changes and rollback targets for production authorization.
- [x] After authorization, run no-send preflight and existing deployment smoke checks, perform the documented stable release/configuration switch, and verify live site health plus both publisher routes without unnecessary report regeneration.
- [x] Add redirect tests asserting the Pages destination and query/hash preservation, and documentation artifact tests asserting `/docs/index.html` exists.
- [x] Build only MkDocs under `/docs/` plus the root compatibility redirect; remove Astro/Node dependencies and publication ledger from Platform website CI. Update docs navigation links to Pages.
- [x] Move calendar configuration into its owner directory and verify provenance/calendar tests; remove remaining website directory only after the dependency inventory is clear.
- [x] Run Platform full gate and strict docs/locale navigation checks.
- [ ] Open and merge final Platform PR after required checks.
- [ ] Recheck clean primary checkouts before fast-forwarding; remove only task worktrees and branches proven merged, preserving ignored work and unmerged changes. Report PR URLs, merged SHAs, validation, live cutover status, rollback target, and remaining work.

## Plan self-review

The additive Platform interface PR precedes Pages because inspection found direct backend imports in the existing website build. This refines the spec's boundary-audit step without changing the intended final ownership. Pages precedes Deploy; production precedes Platform frontend removal. All five review-focus conditions have explicit checks, archive/history preservation remains a required inventory step, and code merges are distinguished from production authorization and live verification.
