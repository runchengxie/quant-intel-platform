# Engineering Improvement Roadmap

[中文页面](roadmap.md)

This roadmap consolidates follow-up items from the 2026-07-31 code-quality audit and sits alongside `refactor-plan-etl-report.md`, which records completed file splits. It tracks plans and does not itself change code.

Status: ✅ complete, ⬜ pending. Completed items include the merge PR and date where recorded. High-priority work protects core behavior from regressions. Medium-priority work removes transitional compatibility layers and complexity. Low-priority work adjusts configuration.

## High priority

### 1. Automated test gate — ✅

Originally, `cross-market.yml` and `tushare-daily.yml` only committed data snapshots and did not run pytest. The local `.githooks/pre-push` was a no-op (`exit 0`), so tests blocked neither merges nor deployment.

Historical progress (PR #54, 2026-07-31, later reverted): a separate `.github/workflows/pytest.yml` once ran on pushes to `main` and every PR, checked out recursive submodules, installed `uv`, ran `uv sync --group dev`, and then `uv run pytest`. Recursive checkout also enabled cross-repository contract tests. That gate exposed pre-existing failures including `test_ai_stock_picker_presentation` and `test_submodule_contracts`, which are covered by item 12 below.

Current state: `public-quality.yml` runs `project_tools/check_all.py --scope all --strict-tools` on PRs and pushes to `main`, including public-boundary checks and package build. The pre-push hook, installer, and branch interception logic have been removed. Production-data access and deployment validation remain separate manual workflows.

### 2. Coverage blind spots — ✅

`coverage.source` originally listed only `daily_messenger`, leaving four other packages outside the gate. PR #47 (2026-07-31) added `a_share_daily`, `a_share_analysis`, `tushare_jobs`, and `ops_common`, so reports cover all five packages. Historical coverage was about 15%. The threshold was first raised from 1 to 10 to prevent obvious regressions, with a plan to increase it toward 70 as tests are added. Re-measure with the full offline suite before raising the threshold.

### 3. Cross-repository model contract checks — ✅

`tests/test_ai_stock_picker_shadow.py:65` previously skipped when submodules were absent. PR #54 used recursive submodule checkout in CI, so CI runs the consistency check while local development can still skip when submodules are not initialized.

### 4. Unit tests for active modules — ✅

PR #48 added offline tests for `src/a_share_analysis/value_regime_weekly.py`, covering `compute_features`, `assign_regime`, `historical_patterns`, and `load_weekly_returns`. Coverage rose from zero to about 30%. Rendering and Lark delivery IO/CLI layers remain outside that test set.

## Medium priority

### 5. Compatibility re-export layers — main item ✅, three sub-items ⬜

- PR #57 removed the `src/a_share_daily/delivery/report_delivery.py` re-export shell. Forty-seven borrowed symbols now use explicit submodule calls. Five tests still patched the old shell and were subsequently fixed to patch `senders` or `state`.
- Remove `_fetch_gemini_market_news` from `src/daily_messenger/etl/fetchers/ai_news.py` after Gemini callers migrate. It currently forwards to the same-named implementation for backward compatibility.
- `src/a_share_daily/daily_watch20_validation/__init__.py` is empty while re-exports remain in `daily_watch20.py:31-58`. Either move the symbols back or add real package-level exports.
- Remove `_legacy_chat_id()` from `src/a_share_daily/delivery/targets.py:107` only after confirming no real data source uses that fallback.

### 6. Split high-complexity functions — ⬜

Twenty-three functions exceed McCabe complexity 15. The highest recorded values are:

| Function | Complexity |
| --- | ---: |
| `src/a_share_daily/freshness.py:render_freshness_section` | 28 |
| `src/a_share_daily/delivery/report_delivery.py:_deliver_markdown_files_and_images` | 23 |
| `src/daily_messenger/etl/fetchers/btc_flow.py:_fetch_sosovalue_latest_flow` | 22 |
| `src/a_share_daily/delivery/report_delivery.py:_deliver_morning_routes` | 22 |

Continue splitting multi-branch rendering and multi-source fetch functions using the repository's existing C901 refactoring patterns.

### 7. Remove transitional scripts and split dual-purpose files — ⬜ (7A complete)

- PR #61 removed `scripts/check_mdp_reference_consistency.py` after the MDP migration and TuShare fallback removal made it obsolete. Its two transitional `_compare` tests were removed as well.
- `src/a_share_analysis/factor_tools/minute_factor_smoke.py` (1,118 lines) still combines a debugging smoke tool and production batch downloader. Split it into distinct `smoke` and `batch_download` entry points in a separate change.

### 8. Smoke tests for operational scripts — ✅

Three scripts received smoke tests: PR #51 covered `refresh_a_share_index_daily.py`, PR #52 covered `check_index_daily_freshness.py`, and PR #53 added a syntax smoke test for the thin `evening_review_pipeline.py` orchestrator. The fourth script, `check_mdp_reference_consistency.py`, was deleted under item 7, so no test was needed. The item is complete through three tests and one deletion.

## Low priority

### 9. Narrow lint exemptions for scripts — ✅

PR #50 restored C90 complexity checks for `scripts/**`. Two existing functions slightly exceed 15 and have targeted per-file exemptions pending refactoring: `check_daily_watch20_producer_freshness.py::check` (16) and `send_hotsector_client_preview.py::main` (17). The `project_tools/**` exemption remains because those gate scripts have test coverage. The same PR removed an unused pytest import so full Ruff checks pass.

### 10. Narrow broad `except` exemptions — low-risk subset complete, remainder pending

Of 73 `# noqa` suppressions, 57 were `BLE001` broad `except Exception` suppressions, mostly in fetchers. PR #59 narrowed nine local JSON/file-IO cases to `(json.JSONDecodeError, OSError)` or `OSError` without changing control flow. About 46 fetch-layer cases intentionally handle provider tokens, network edge cases, or multiple-provider fallback; review each call site before narrowing.

### 11. Ignore coverage artifacts — ✅

No change was needed: `.gitignore` already lists `.coverage`, `.coverage.*`, and `coverage.xml` at lines 39–43.

### 12. Fix pre-existing test failures — ✅

PR #55 fixed failures exposed by the proposed pytest gate. Some failures were caused by missing submodule checkouts (`FileNotFoundError`), not faulty assertions, so affected tests now skip when submodules are absent, consistent with `test_ai_stock_picker_shadow.py`. The original report at PR #55 recorded 718 passed, 91 skipped, and zero failed. A later snapshot recorded 716 passed, 91 skipped, and zero failed. The maintainability ratchet was also restored by wrapping four long test assertions and one display string.

### 13. Reduce complexity-rule exemptions — ⬜

On 2026-09-26, temporarily enabling `PLR0911` and `PLR0913` across the repository surfaced 134 existing diagnostics, mostly excessive argument counts. Removing global ignores at once would block checks on existing debt. Two ignores remain, with a per-file/per-rule no-growth ratchet; `PLR0917` was not configured because it has no effect without the preview rules enabled.

The maintainability ratchet found 10 functions over 100 lines against a budget of 9. Splitting the long orchestration function in `weekly_basket_command.py` returned the count to 9. The maintainability and PLR ratchets are now part of the PR quality workflow. Tighten budgets incrementally.

## Progress summary

| Item | Status | Recorded PR |
| --- | --- | --- |
| Automated test gate | Complete; PR/main CI runs the full quality gate and the repository pre-push hook was removed | Current task PR |
| Coverage scope | Complete | #47 |
| Cross-repository contract check | Complete via recursive submodule checkout | #54 |
| `value_regime_weekly` unit tests | Complete | #48 |
| Compatibility re-export cleanup | Main item complete; three sub-items pending | #57 |
| High-complexity function splits | Pending | |
| Transitional scripts and dual-purpose split | Pending | |
| Operational-script smoke tests | Complete: three tests, one obsolete script removed | #51, #52, #53, #61 |
| Script lint exemptions | Complete | #50 |
| Broad `except` cleanup | Nine low-risk cases complete; about 46 remain for domain review | #59 |
| Coverage artifact ignores | Complete; no code change needed | |
| Pre-existing test failures | Complete | #55 |
| Complexity-rule exemptions | Ratchet in place; further reductions pending | |

## Submodule scope

The three submodules (`a-share-factor-core`, `ai-stock-picker`, and `hot-sector-screener`) have their own Ruff configurations, manageable size, and owner-submodule plus CLI/JSON handoff model. Their complexity governance remains with each repository's own `pyproject.toml`; this roadmap did not audit their internals.

## Overall assessment

The main project had zero Ruff violations and clear module boundaries at the time of this assessment. `ty check` still reported 15 unresolved diagnostics in `cli.py`, `news_heat.py`, `ai_selection_receipt.py`, `daily_watch20_delivery_receipt.py`, and `tushare_jobs/cli.py`; the type gate had not yet passed. The next priorities were resolving those diagnostics, reviewing the coverage threshold, and continuing complexity and compatibility cleanup. Check current CI output before treating these historical counts as current.
