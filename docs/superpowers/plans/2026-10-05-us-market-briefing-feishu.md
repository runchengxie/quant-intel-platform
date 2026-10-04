# U.S. Market Briefing Feishu Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed, offline consumer and no-send preview for reviewed `market.briefing.v1` bundles in quant-intel-platform.

**Architecture:** Place the adapter beside the existing global-market reporting flow under `daily_messenger.daily_report`. Reuse `ops_common.platform_publication.verify_platform_publication` for the generic manifest, path and SHA-256 boundary, then validate the briefing/review-specific contract and render a deterministic preview. Do not call Feishu or resolve any destination in this milestone.

**Tech Stack:** Python 3.11+, `jsonschema` 4.x, existing argparse CLI and `research_contracts` publication verifier, pytest with synthetic JSON fixtures, MkDocs.

**Spec:** `docs/superpowers/specs/2026-10-05-us-market-briefing-feishu-design.md`

## Global Constraints

- Consumer ID remains `market-intel`.
- Do not import quant-market-briefing source code or add a dependency on its package.
- Accept only `market.briefing.v1` and `market.source-review.v1` in this implementation.
- Formal preview requires a `validated_draft` and a separate source-review record approving exactly every final claim.
- Preserve producer bytes; rendering must not rewrite `brief_text` or add market facts.
- No Feishu API, CLI, credential, destination, schedule, live market data or model call in the implementation or CI.
- Use synthetic example URLs/domains and clearly synthetic report identity in tests and documentation.
- Any live sender, channel selection and deployment schedule belongs to a separately scoped task in quant-intel-deploy.

## Review Focus

- `internal` packages must fail when preview runs without explicit internal opt-in.
- Review records must bind the exact evidence, analysis and briefing bytes; a modified unmanifested evidence or analysis file must fail.
- Final claim IDs must match the review decisions exactly, including duplicate claim IDs in malformed records.
- A repeated invocation must remain a preview and must not gain send behavior from environment variables or runtime configuration.
- Filesystem paths and symlinks must not resolve outside the publication bundle.

---

### Task 1: Validate U.S. briefing publication bundles

**Files:**
- Create: `src/daily_messenger/daily_report/us_market_briefing.py`
- Create: `src/daily_messenger/daily_report/schemas/market.briefing.v1.json`
- Create: `src/daily_messenger/daily_report/schemas/market.source-review.v1.json`
- Create: `tests/fixtures/publications/us_market_briefing/{publication-manifest.json,briefing.json,review.json,evidence.json,analysis.json}`
- Create: `tests/daily_report/test_us_market_briefing.py`
- Modify: `pyproject.toml` to add the runtime validator dependency and package schema resources
- Modify: `uv.lock`

**Interfaces:**
- Consumes: `ops_common.platform_publication.verify_platform_publication(manifest_path, allow_internal=...)`.
- Produces: `load_us_market_briefing_bundle(manifest_path: str | Path, *, allow_internal: bool = False) -> UsMarketBriefingBundle`.
- `UsMarketBriefingBundle` exposes manifest identity, audience, validated briefing/review mappings and resolved source artifact paths as immutable fields.

- [ ] **Step 1: Add failing bundle validation tests**

Create a synthetic five-file bundle in `tests/fixtures/publications/us_market_briefing/` with five Chinese paragraphs, unique final claim IDs, HTTPS `example.com` source URLs, one decision per claim, and review hashes computed from the exact evidence, analysis and briefing bytes.

Add tests asserting a valid internal bundle is rejected without `allow_internal=True` and accepted with it; a public bundle is accepted in public mode; unsupported schema versions, extra or missing briefing/review artifacts, incorrect consumer IDs, missing files, traversal/symlink escapes, hash tampering, date/run mismatches, non-`validated_draft` status, invalid sources, unknown contract fields, non-five-paragraph text, `brief_text` mismatch, and missing/extra/duplicate/non-approved claim decisions all raise `ValueError` or `FileNotFoundError` before returning a bundle.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `uv run pytest tests/daily_report/test_us_market_briefing.py -q`

Expected: FAIL because `load_us_market_briefing_bundle` and `UsMarketBriefingBundle` are not implemented.

- [ ] **Step 3: Implement the bundle loader**

Implement `UsMarketBriefingBundle` and `load_us_market_briefing_bundle` in `src/daily_messenger/daily_report/us_market_briefing.py`. Add `jsonschema>=4.23,<5` as an explicit runtime dependency and package frozen copies of the producer's v1 briefing and review JSON Schemas as consumer-supported contract snapshots. Require exactly one briefing and one review artifact for `market-intel`, require the corresponding schema versions, and delegate generic path/audience/hash checks to `verify_platform_publication`. Load only fixed sibling names `evidence.json` and `analysis.json`, resolve them beneath the bundle root, and verify them against the review hashes. Run Draft 2020-12 validation with format checking, then validate same market date and run identity, review time not earlier than briefing generation, `brief_text` equality, exact claim-decision set and all decisions `approved`. Do not import producer code.

- [ ] **Step 4: Run focused tests and ensure they pass**

Run: `uv run pytest tests/daily_report/test_us_market_briefing.py -q`

Expected: PASS for all valid and fail-closed cases; no test accesses the network.

- [ ] **Step 5: Commit the bundle contract implementation**

```bash
git add src/daily_messenger/daily_report/us_market_briefing.py tests/fixtures/publications/us_market_briefing tests/daily_report/test_us_market_briefing.py
git commit -m "feat: validate US market briefing bundles"
```

### Task 2: Render deterministic no-send previews

**Files:**
- Modify: `src/daily_messenger/daily_report/us_market_briefing.py`
- Modify: `src/daily_messenger/cli.py`
- Create: `tests/daily_report/test_us_market_briefing_cli.py`
- Modify: `tests/test_cli_pipeline.py` only for top-level CLI parser/dispatch coverage

**Interfaces:**
- Consumes: `load_us_market_briefing_bundle` from Task 1.
- Produces: `render_us_market_briefing(bundle: UsMarketBriefingBundle) -> str` and the CLI command `dm us-briefing-preview --manifest PATH [--allow-internal]`.
- CLI output is JSON with `schema_version: "market.briefing.preview.v1"`, `status: "preview"`, `dry_run: true`, `market_date`, `run_id`, `revision`, `audience`, `headline`, `brief_text`, and `sources` (each retaining `id`, `title`, `publisher`, `url`, and `published_at`).

- [ ] **Step 1: Add failing render and CLI tests**

Assert `render_us_market_briefing` returns the headline, unchanged `brief_text`, and all declared source links in deterministic order. Assert `dm us-briefing-preview` emits parseable JSON with the preview fields above. Assert it rejects internal bundles without opt-in and malformed bundles with a nonzero exit. Set environment variables resembling Feishu credentials and assert the command still never invokes subprocesses or HTTP requests.

- [ ] **Step 2: Run focused tests and confirm they fail**

Run: `uv run pytest tests/daily_report/test_us_market_briefing_cli.py -q`

Expected: FAIL because the renderer and CLI command are not implemented.

- [ ] **Step 3: Implement renderer and preview command**

Add the deterministic renderer and a dedicated argparse command in `src/daily_messenger/cli.py`. Keep the command offline: it loads the bundle, prints the preview JSON to stdout and exits. It must not read a destination variable, instantiate a sender, call `post_feishu.py`, or write a `sent` state. Add a focused dispatch handler with error logging that does not print source payload secrets or traceback data.

- [ ] **Step 4: Run focused tests and ensure they pass**

Run: `uv run pytest tests/daily_report/test_us_market_briefing_cli.py tests/test_cli_pipeline.py -q`

Expected: PASS, with existing CLI behavior unchanged and the fake network/sender assertions untouched.

- [ ] **Step 5: Commit the preview path**

```bash
git add src/daily_messenger/daily_report/us_market_briefing.py src/daily_messenger/cli.py tests/daily_report/test_us_market_briefing_cli.py tests/test_cli_pipeline.py
git commit -m "feat: add offline US briefing preview"
```

### Task 3: Document the supported consumer and handoff

**Files:**
- Modify: `docs/us-market-briefing.md`
- Modify: `docs/us-market-briefing.en.md`
- Modify: `docs/superpowers/specs/2026-10-05-us-market-briefing-feishu-design.md` to change the status from draft to approved/implemented where applicable
- Test: `uv run mkdocs build --strict` and `uv run python project_tools/check_locale_navigation.py --site-dir site`

**Interfaces:**
- Consumes: `dm us-briefing-preview --manifest PATH [--allow-internal]` from Task 2.
- Produces: bilingual operating notes identifying the accepted schema versions, synthetic no-send preview command, source-review gate and the remaining private-deployment/live-send work.

- [ ] **Step 1: Update both language pages**

Document the supported v1 bundle inputs, the separate approval record requirement, the command's offline/no-send guarantee, and that real audiences, schedules, credentials, delivery idempotency and recovery remain owned by quant-intel-deploy and a future separately approved rollout.

- [ ] **Step 2: Run documentation validation**

Run: `uv run mkdocs build --strict`

Run: `uv run python project_tools/check_locale_navigation.py --site-dir site`

Expected: both commands exit zero and both language pages are present in the rendered site.

- [ ] **Step 3: Commit the documentation**

```bash
git add docs/us-market-briefing.md docs/us-market-briefing.en.md docs/superpowers/specs/2026-10-05-us-market-briefing-feishu-design.md
git commit -m "docs: document US briefing preview contract"
```

## Later, separately scoped work

- Add a real sender, destination configuration, receipt persistence and idempotent retry only after the user chooses the Feishu audience and approves the live-delivery scope.
- Add the immutable producer/consumer pins, U.S. trading calendar schedule, bounded retry window, recovery and private runtime state in quant-intel-deploy.
- Keep model/research evaluation work in its existing TODO section. It is not part of this implementation plan.
