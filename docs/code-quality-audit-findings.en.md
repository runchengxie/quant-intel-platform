# Code-Quality Audit Record and Follow-up Proposals

[Chinese version](code-quality-audit-findings.md)

> Historical audit record. The original inventory was performed on 2026-07-31, with selected status updates through 2026-09-08. Counts and findings below are dated snapshots, not current gate results. The former `a-share-factor-core`, `ai-stock-picker`, and `hot-sector-screener` submodules have since been retired and removed. Current repository ownership boundaries are in `AGENTS.md`.

This page preserves the audit evidence and the disposition recorded for its findings. The audit proposed changes; it did not itself modify code.

## Snapshot and later status notes

The 2026-07-31 review covered the `market-intel` repository and three submodules that have since been retired. By 2026-09-08, `scripts/dev/maintainability_metrics.py --json --ratchet` reported 106 lines longer than 100 columns, 9 functions longer than 100 lines, 2 files longer than 800 lines, and no inline `C901` suppressions. The ratchet passed at that snapshot. These values should not be used as today's baseline.

The repository now runs its complete quality gate and package build through `public-quality.yml` for pull requests and pushes to `main`; the former `pr-light.yml` and pre-push hook installer were removed. `pytest.yml.disabled`, `cross-market.yml.disabled`, and `tushare-daily.yml.disabled` remain disabled files. `.gitignore` includes `.coverage`, `.coverage.*`, and `*.cover`.

This audit is the detailed evidence appendix to [`roadmap.md`](roadmap.md), which tracks actions and completion status.

## Test coverage and CI observations

The audit initially identified the following issues and proposals:

| Finding in the 2026-07-31 snapshot | Recorded disposition or proposal |
| --- | --- |
| The former `pytest.yml` was disabled, and the old cross-market / Tushare workflows only committed data snapshots. | Resolved by the current `public-quality.yml`, which runs `project_tools/check_all.py --scope all --strict-tools` and builds the package. Cross-repository owners retain their own quality gates. |
| `coverage.source` listed only `daily_messenger`, leaving four major packages outside the then-configured `fail_under=70` scope. | The source list now includes all five packages. The current `fail_under` is 10, so the original 70% threshold proposal is not reflected in the current configuration. |
| `tests/test_ai_stock_picker_shadow.py` could skip a cross-repository model-contract check when a submodule was absent. | The audit proposed making the check fail or ensuring CI initializes the required dependency. The referenced submodule has since been retired; this finding must be interpreted under current ownership and tests. |
| `src/a_share_analysis/value_regime_weekly.py` was called by `scripts/weekly_recap.sh` without a direct unit test. | Resolved: `tests/test_value_regime_weekly.py` now covers the module. |
| Four operational scripts lacked smoke tests: `check_index_daily_freshness.py`, `check_mdp_reference_consistency.py`, `evening_review_pipeline.py`, and `refresh_a_share_index_daily.py`. | The audit proposed syntax and key-behavior checks. `check_mdp_reference_consistency.py` was later removed with the legacy TuShare path and its `_compare` transition test. |
| The repository-root `.coverage` file was not ignored. | Verified fixed: `.gitignore` now ignores `.coverage`, `.coverage.*`, and `*.cover`. |

The same audit snapshot recorded 15 `ty check` diagnostics across `cli.py`, `news_heat.py`, `ai_selection_receipt.py`, `daily_watch20_delivery_receipt.py`, and `tushare_jobs/cli.py`. It also rejected an earlier claim of 99.7% return-type coverage as unsupported. This count is historical; use the current type-check output for present status.

## Compatibility layers and complexity

- `report_delivery.py` had re-exported roughly 50 private symbols from `senders`, `state`, `targets`, and `io_util`, preserving monkeypatch paths while increasing file size and exposing duplicate namespaces. The audit proposed moving tests to patch the owning modules and then removing the compatibility exports. A later refactor split delivery responsibilities while retaining compatibility exports for callers and tests.
- `_fetch_gemini_market_news` in `daily_messenger/etl/fetchers/ai_news.py` was identified as a forwarding wrapper. The audit proposed removing it after callers migrated.
- Thirteen validation/normalization helpers were re-exported from `daily_watch20.py`. Their exports were removed on 2026-08-01; tests import the validation subpackage directly.
- `_legacy_chat_id()` in `a_share_daily/delivery/targets.py` was identified as an internal fallback. The original proposal was to remove it only after confirming no live configuration depended on it.
- Twenty-three functions were reported above McCabe complexity 15. The highest listed values were `render_freshness_section` (28), `_deliver_markdown_files_and_images` (23), `_fetch_sosovalue_latest_flow` (22), and `_deliver_morning_routes` (22). These are dated audit measurements, not a current complexity report.
- `scripts/check_mdp_reference_consistency.py` was a transition validator for the legacy TuShare path. It and the associated `_compare` test were removed after the MDP migration (PR #61).
- The audit proposed separating the 1,118-line `minute_factor_smoke.py` into debugging and production batch-download entry points. A later approved change migrated nine connected factor scripts into `src/a_share_analysis/factor_tools/`; this page does not claim that the proposed two-entry-point split was completed.

The factor-tool migration recalculated `PROJECT_ROOT`, converted internal imports to package imports, changed production shell callers to `python -m a_share_analysis.factor_tools...`, and updated tests. The package was included in `ty` checks. A narrowly scoped allowance covered the external `quant_market_data_platform` import, and pandas typing mismatches were addressed without runtime changes. Complexity metrics excluded the migrated package to avoid treating a physical move as a ratchet regression. Focused tests were added for volume-calendar labels, factor expansion, and Hermite metadata helpers.

## Lint and exception-handling review

The original audit noted broad Ruff exemptions for `scripts/**` and `project_tools/**`, including complexity and style rules, and proposed restoring at least C90 for scripts. It also counted 73 `# noqa` comments, 57 of them for `BLE001`, mostly in data-fetching code, and proposed gradually narrowing broad exception handling where doing so preserves degradation behavior.

The review did not recommend mechanically replacing every `except Exception`:

- In `review.py`, data-read failures leave a section unavailable for that trading day while allowing the rest of the report to render.
- In `pipeline.py`, a failed chart can be omitted without aborting other charts.
- External-source fetchers use broad catches as part of source-level degradation and status reporting.

One subprocess handler in `ai_selection_receipt.py` was narrowed to `(subprocess.SubprocessError, OSError)` because those exceptions covered its delivery-error reporting behavior.

The audit also evaluated whether to consolidate Lark CLI calls into a shared client and recommended keeping the specialized implementations separate. `senders.py`, `daily_watch20_lark_delivery.py`, and `style_replica_bridge` differ in timeout, working directory/environment, dry-run behavior, receipts, idempotency, admission guards, and target type. A common wrapper would add coupling for little benefit. The file-specific S603 suppressions were retained because each local command is constructed without external input.

## Repository and team observations

At the time of the audit, the three submodules used owner-submodule plus CLI/JSON handoff patterns and had independent Ruff configuration. The audit described 145 modules across five responsibility-oriented packages, noted existing architecture and contract documentation, and identified coverage as the main maintainability risk. It also noted that `AGENTS.md` described single-person maintenance; if multi-person collaboration resumes, CODEOWNERS and review cadence should be revisited.

These observations refer to the historical repository shape. The former submodules have been removed, and strategy research / model training / backtesting now belong to owner repositories such as `quant-research`, `quant-platform`, and `strategy-pipeline`. The current repository should consume their public CLIs or versioned artifacts rather than maintain duplicate research implementations.
