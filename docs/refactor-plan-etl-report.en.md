# ETL and Report-Delivery Refactoring Record

[Chinese version](refactor-plan-etl-report.md)

> Historical record. The migration status below reflects the repository after the refactors described here. Earlier proposals retained in this document are historical context, not current work items. Current ownership boundaries are documented in the repository's `AGENTS.md`.

This record tracks the decomposition of `run_fetch.py`, `report_delivery.py`, dashboard payload generation, AI-news fetching, and DailyWatch20 validation. The work moved code into responsibility- or source-specific modules while retaining compatibility exports where callers and tests depended on the original module paths.

## Outcome at the time of this record

| File | Before | Result recorded here |
| --- | ---: | --- |
| `daily_messenger/etl/run_fetch.py` | 860 lines | 693 lines; source fetchers moved to dedicated modules, leaving orchestration and compatibility exports |
| `a_share_daily/delivery/report_delivery.py` | 1,396 lines | 696 lines; delivery targets, senders, state, and utilities moved to `io_util.py`, `targets.py`, `senders.py`, and `state.py` |
| `daily_messenger/dashboard/payload.py` | 1,711 lines | 181 lines; helpers, state, aggregations, terminal data, and coverage moved to separate modules |
| `daily_messenger/etl/fetchers/ai_news.py` | 1,317 lines | 199 lines; common settings, parsing, provider, and feed logic moved to submodules |
| `a_share_daily/daily_watch20.py` | 1,182 lines | 587 lines; 13 validation helpers moved into `daily_watch20_validation/` |

The much larger `run_fetch.py` and `report_delivery.py` line counts quoted in early proposals (about 1,938 and 1,813) were pre-refactor measurements. The maintainability ratchet for files over 800 and 1,200 lines was lowered after the decompositions.

## ETL orchestration

The fetcher package contains modules for AI news, FMP, Cboe Put/Call, EDGAR, FRED, AAII sentiment, Hong Kong data, quote aggregation, event normalization and retrieval, and BTC/ETF flows. `run_fetch.py` now combines their results into `raw_market.json`, `raw_events.json`, and `etl_status.json`, in addition to path handling, cache checks, configuration, and orchestration.

An earlier section of the source note listed `_fetch_coinbase_spot`, `_fetch_okx_funding`, `_fetch_okx_basis`, quote functions, AI-news functions, and sentiment/BTC payload functions as still awaiting extraction. That list was superseded by the later completion record: the remaining functions were moved to `coinbase_okx.py`, `quotes.py`, `ai_news.py`, `aaii_sentiment.py`, and `btc_flow.py`. Test stubs were updated to patch the owning modules. The resulting `run_fetch.py` was described as an orchestration layer with compatibility exports, not as a list of pending moves.

## Report delivery

Evening rendering helpers moved to `a_share_daily/delivery/_render.py`; IO and formatting helpers moved to `_format.py`. Delivery-target parsing, Hermes / `lark-cli` / webhook senders, state and idempotency, chart freshness, and constants were separated into `targets.py`, `senders.py`, `state.py`, and `io_util.py`.

The original module retained orchestration entry points such as `deliver_morning`, `deliver_evening`, and `run`, plus compatibility re-exports. The recorded refactor did not require external callers or tests to change their imports.

## Factor-tool package migration

The nine scripts listed below were promoted from `project_tools/` into `src/a_share_analysis/factor_tools/` as an explicitly approved migration:

| Previous script | Package module |
| --- | --- |
| `a_share_minute_factor_smoke.py` | `minute_factor_smoke.py` |
| `a_share_factor_walk_forward.py` | `walk_forward.py` |
| `a_share_factor_incremental_experiment.py` | `incremental_experiment.py` |
| `a_share_minute_volume_oos_audit.py` | `volume_oos_audit.py` |
| `a_share_minute_volume_calendar.py` | `volume_calendar.py` |
| `a_share_minute_factor_expand.py` | `minute_factor_expand.py` |
| `a_share_hermite_factor_meta.py` | `hermite_factor_meta.py` |
| `minute_raw_completeness.py` | `minute_raw_completeness.py` |
| `quantall_bridge.py` | `quantall_bridge.py` |

The move required recalculating `PROJECT_ROOT` from `Path(__file__).resolve().parents[1]` to `parents[3]`, replacing script-to-script imports with package imports, and updating the two production shell entry points to use `python -m a_share_analysis.factor_tools...`. The bridge now uses a relative import for `a_share_analysis.quantall`. Tests import the package modules directly and no longer inject `project_tools/` into `sys.path`.

The factor tools were brought into `ty` checking. The external `quant_market_data_platform` import is narrowly allowed as unresolved because that package is supplied by another repository and has no `py.typed` marker. Pandas stub mismatches were addressed with annotations and casts, without changing runtime behavior. Complexity metrics exclude this migrated package so a file move does not inflate the repository-wide ratchet. Three focused test modules were added for volume-calendar labels, factor expansion, and Hermite metadata helpers.

## Decisions and scope recorded

- ETL fetch failures intentionally use broad exception handling to preserve source-level degradation and status reporting. The physical moves did not change that behavior.
- `post_market_review.py` was removed after confirming it had no callers; the canonical implementation is `a_share_daily.review`. `style_replica_bridge` and `quantall.py` remained active features, not dead-code cleanup candidates.
- The factor scripts' earlier classification as research-only, unmigrated `project_tools` code was superseded by the package migration above.
- A-share factor research, model training, backtesting, ablation, and strategy-artifact production now belong to owner repositories such as `quant-research`, `quant-platform`, and `strategy-pipeline`. This repository should consume their public CLI or versioned artifacts rather than reintroduce research implementations.

The historical completion record reported passing `ruff check`, `ruff format --check`, `ty check`, the full pytest suite, and `project_tools/check_all.py --scope all`. Those results describe that recorded revision; run the current project gates before relying on them for a new change.
