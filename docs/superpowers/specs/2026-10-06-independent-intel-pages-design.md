# Independent Quant Intel Pages

Status: proposed; repository inspection complete, implementation and production switch pending.

## Outcome

`quant-intel-pages` owns the public daily report frontend and its GitHub Pages deployment. `quant-intel-platform` owns report production, model commentary, evidence validation, and publication CLI contracts. `quant-intel-deploy` orchestrates production and publishes reviewed public snapshots to Pages. Daily snapshot commits therefore land in Pages alongside frontend changes; Platform history contains framework development and documentation.

## Current state

Inspected Platform `origin/main` at `3318dc9`, Pages at `a67720e`, and Deploy at `7c47a5b`. All primary checkouts were clean. Platform owns the current Astro application under `web/`; Pages preserves an older application and redirects to Platform. Platform's `public-site.yml` combines Astro with MkDocs under `/docs/`. Deploy publishers, chart review tools, path allowlists, and workflow polling select `web/artifacts/public` and `public-site.yml`.

Platform already provides `market_intel_publication`, `market_intel_commentary`, and report refresh capabilities. Its publication path helper accepts a target root and selects `artifacts/public`; these are suitable handoff contracts, subject to verification of every caller.

## Repository ownership

### Pages

Transfer the current maintained Astro application, frontend assets, build adapters, frontend tests, and public monitoring from Platform `web/` into Pages. Preserve existing Pages historical archives and rollback material; inventory collisions before replacing tracked files. Remove the homepage redirect and set the Astro base to `/quant-intel-pages`. Keep current language selection, report rendering, evidence links, downloads, and the five-date public window.

Pages contains no data acquisition, model generation, commentary prompts, or backend implementation. Retire its historical generation entry points only after proving their replacement exists in Platform and recording the immutable rollback revision. Public snapshot validation and rendering adapters may remain. Consumers call the installed Platform CLI or consume versioned files, with no sibling source imports.

Pages owns the website workflow and publication ledger artifact. Preserve the workflow and artifact names expected by Deploy where practical to reduce coupling during the switch. Website CI requires no model credentials.

### Platform

Keep report production, commentary, publication CLI, versioned schemas, and their tests. Move any remaining backend capability out of `web/` before removing that directory. In particular, inspect chart review/import and exchange calendar configuration to assign each to its actual owner.

Publish framework documentation independently at the existing `/quant-intel-platform/docs/` address. The previous report entry point should redirect to Pages, preserving report hashes and query parameters where applicable. Update documentation navigation, README files, repository instructions, quality checks, and public boundary checks to reflect the new ownership.

### Deploy

Point both Asia and US report publishers at Pages and change target paths from `web/artifacts/public/...` to `artifacts/public/...`. Update chart tooling invocation, publication allowlists, report identity checks, ledger retrieval, workflow polling, URL health checks, examples, and smoke tests together. Keep Platform CLI executables and Pages frontend release paths distinct.

Actual private configuration, release aliases, and schedulers require a separately authorized production switch under the repository instructions. Prepare the implementation, no-send verification, and rollback procedure before that approval.

## Alternatives

1. Recommended: transfer the maintained frontend and adapt existing artifact publishers. This restores the requested ownership while retaining current functionality.
2. Keep the frontend in Platform and deploy a copy through Pages. This separates hosting but leaves frontend development and report snapshot commits in Platform.
3. Replace snapshot publication with a new API or object storage service. This can also remove daily snapshot commits from Pages, but adds infrastructure outside this adjustment's scope.

## Handoff and failure behavior

Keep current report schemas, evidence identifiers, timestamps, content hashes, explicit public manifests, and private archive retention. Reject invalid inputs and paths before commit or publication. A failed website build or health check must not advance the publication receipt to success. Keep owner versions pinned for production and verify compatibility before switching.

Inventory running publisher jobs, pending branches and receipts, stable release aliases, credentials references, and downstream URLs before modifying production. Pending publication state must remain recoverable; do not copy a completed Platform receipt into Pages and assume it proves publication there.

## Implementation order

1. Audit frontend/backend boundaries, archive collisions, public URL references, and publisher state contracts.
2. Restore Pages frontend, workflow, adapters, and tests; merge the provider PR after required gates pass.
3. Adapt Deploy publishers to the merged Pages contracts and verify offline publication and failure recovery; merge its PR.
4. Prepare stable release pins and production configuration changes with a documented rollback target; obtain production-switch authorization, then perform no-send checks, switch, and verify the live website and both publisher routes.
5. Remove Platform frontend once production and rollback no longer depend on it; retain backend contracts and documentation publishing, then merge its PR.

## Acceptance and validation

Run each affected repository's required local quality gates and required GitHub checks. Pages must pass Astro checking/build, Python and Node tests, and browser checks for representative Asia and US reports, locale selection, downloads, and evidence links. Deploy must pass smoke tests covering both publishers, allowlists, ledger/workflow verification, idempotency, and interrupted publication recovery. Platform must pass its full quality gate and contract tests after frontend removal.

Verify that daily publication branches target Pages, frontend CI uses no secrets, backend CLI works independently of a Pages checkout, Platform docs retain their address, and the old report URL reaches Pages. Report code merge, production switch, and live verification as separate outcomes. Do not rewrite Git history.
