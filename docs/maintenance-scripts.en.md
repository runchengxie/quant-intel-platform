[Chinese version](maintenance-scripts.md)

# Maintenance scripts and experiment-code boundaries

This repository contains production entry points, low-frequency operations commands, local diagnostics, and research tools. Classify a script before deciding its test, release, and alerting requirements.

## Production entry points

| Entry point | Purpose | Scheduling / quality gate | Quality requirements |
| --- | --- | --- | --- |
| `dm` | Daily-report ETL, scoring, rendering, and BTC helper commands | Local report jobs; PR/main CI | Ruff, formatting, ty, pytest with coverage, and contract tests |
| `marketops` | TuShare data jobs | Windows Task Scheduler / Linux systemd; PR/main CI | Ruff, formatting, ty, and TuShare unit tests |
| `a-share-daily` | A-share morning/evening reports, charts, and Feishu factual-layer delivery | `scripts/morning_pipeline.sh`, `scripts/evening_pipeline.sh`, `scripts/windows/*.ps1`, and Hermes schedules | Ruff, ty, and focused pytest coverage; ty covers all `src/` code |

## Low-frequency operations commands

| Command | Purpose | Notes |
| --- | --- | --- |
| `dm btc init-history` | Download Binance historical candles and consolidate Parquet | Higher network and disk use; check `out/btc/` or the configured output directory first |
| `marketops tushare stock-st backfill` | Backfill historical ST data | Uses TuShare quota; specify a date range where possible |
| `marketops tushare listed-company backfill --consolidate` | Refresh all listed-company data | Uses TuShare quota; check resumability and output format |
| `scripts/refresh_tushare_report_datasets.sh YYYYMMDD` | Fetch report-critical theme, money-flow, concept, and limit-move data; theme mapping and four event-confirmation sources default to a rolling five-trading-day backfill | Skipped by default. Set `A_SHARE_ENABLE_TUSHARE_PREMIUM=1` to call the APIs. If staging validation fails, preserve last-known-good data and write a failure receipt |
| `scripts/windows/install_scheduled_tasks.ps1` | Register Windows morning/evening report tasks | Defaults to 07:00 and 19:00; the stock preview is part of the morning task. Re-register with `-Force` after changing times |

## Scheduled and diagnostic scripts

These scripts are scheduled by Windows Task Scheduler, Linux systemd/cron, or Hermes, or run manually as part of the production path.

| Script | Purpose |
| --- | --- |
| `scripts/morning_pipeline.sh` | Thin morning-pipeline wrapper: detects the latest trading day, prefetches news and cross-market data, then calls `a-share-daily morning` |
| `scripts/evening_pipeline.sh` | Evening pipeline for data refresh, charts, post-close commentary, and US pre-market preview; the single weekday 19:00 CST cron entry |
| `scripts/refresh_tushare_daily.sh` | Asian daily-data refresh entry for the systemd timer after 15:30 CST; the scheduled daily fetch for A-shares and Japan/Korea markets |
| `scripts/publish_a_share_current.sh` | Publish the current A-share contract after TuShare refresh: build and validate `daily_clean` and the stock universe, repair cumulative raw manifests, then promote artifacts |
| `scripts/local_fetch_cross_market.sh` | Linux local cross-market fetch entry after 05:00 CST and before the 07:00 Hermes run; Layer 2 of the three-layer fallback |
| `scripts/refresh_weekly_style_factors.sh` | Saturday 08:15 compatibility entry that calls the `quant-research` owner and preserves schedule/receipt paths |
| `scripts/weekly_recap.sh` | Weekly recap entry for the value-factor regime report and morning-report-based market recap |
| `scripts/morning_product_supervisor.sh` | Loads the morning report's credentials and destinations, then supervises DailyWatch20, D11-H5, and report delivery |
| `scripts/daily_watch20_delivery.sh` | Validates a `strategy-pipeline` DailyWatch20 artifact and invokes this repository's delivery adapter |
| `scripts/ensure_hermes_gateway.sh` | Ensures the systemd-managed Hermes Gateway is active without restarting a healthy instance |
| `scripts/fetch_ai_market_news.py` | Thin CLI wrapper for structured AI-market-news fetching |
| `scripts/refresh_a_share_index_daily.py` | Refresh daily A-share index data |
| `scripts/send_daily_watch20.py` | Sends a validated, already-published DailyWatch20 artifact to configured destinations |

### Freshness watchdogs

These scripts independently check artifact freshness. Matching `.sh` wrappers schedule them where needed.

| Script | Checks |
| --- | --- |
| `scripts/check_daily_watch20_producer_freshness.py` | DailyWatch20 producer and publication freshness; internal operations check that uses the supervisor's systemd failed state as an upstream escalation signal |
| `scripts/check_index_daily_freshness.py` | Freshness of the A-share `index_daily` snapshot |

## `project_tools/`

| Script | Users | Called by CI | Purpose |
| --- | --- | --- | --- |
| `check_all.py` | Developers, GitHub Actions | Yes, full quality gate | Runs Python, shell, PowerShell, and JavaScript checks |
| `update_cli_help.py` | Developers, GitHub Actions | Yes, called by the full gate | Detects drift in CLI documentation |

Register new scripts in the relevant table and document whether they are called by CI or production schedules, which environment variables or secrets they require, whether they access the network/use quotas/write large files, and whether failure blocks release.

## Compatibility entry points and legacy inventory

| Entry point | Status | Owner | Handling |
| --- | --- | --- | --- |
| `scripts/evening_review_pipeline.py` | Compatibility entry for an old scheduled job | Operations scripts | New deployments should use `scripts/evening_pipeline.sh` or `scripts/windows/evening_pipeline.ps1`. Retained because `tests/test_evening_review_pipeline_script.py` still references it |
| `src/ops_common/notify_email.py` | No current call sites | `marketops` operations | No repository references remain. Before re-enabling email alerts, add tests and documentation; otherwise it can be removed in a later cleanup |

`src/a_share_analysis/post_market_review.py` was a post-market commentary compatibility wrapper. Its canonical implementation moved to `a_share_daily.review`; schedulers use `a-share-daily evening/review`. The unused wrapper has been deleted.

## A-share daily CLI: `a_share_daily`

`src/a_share_daily/` owns production morning/evening report generation, chart output, and delivery of the factual layer through Feishu. It depends on local `DATA_PLATFORM_ROOT`, owner public CLIs/artifacts, and `data-snapshots/`. Existing tests cover delivery, news contracts, CLI smoke behavior, missing-data boundaries, and deployment checks.

Implemented capabilities:

1. `a-share-daily doctor` checks script permissions, the `market-data-platform` repository, data lake, latest snapshots, AI key, Feishu destinations, and `lark-cli`. With `--live`, it also checks Task Scheduler on Windows or systemd timers on Linux, plus Hermes schedules.
2. `refresh_tushare_report_datasets.sh` fetches supplemental theme, money-flow, concept, and limit-move data. These APIs are disabled by default and require `A_SHARE_ENABLE_TUSHARE_PREMIUM=1`. Candidate pools, research computation, and official DailyWatch20 artifacts belong to `quant-research` / `strategy-pipeline`; this repository validates, renders, and delivers published artifacts only.
3. Root-project `ty check` covers all source code under `src/`, including the daily CLI, pipelines, data, review, cross-market, charts, and delivery modules.
4. Pipeline tests cover missing core daily data, premium TuShare being skipped by default, missing optional owner artifacts, and the return/placeholder-chart behavior when `moneyflow_ths` is unavailable.

Maintenance priorities:

1. Keep new source files within the full `ty` check; do not widen exclusions to bypass type errors.
2. Continue splitting `report_delivery` and remaining long-flow helpers. The root project no longer has the historical `C901` exemption, so Ruff should catch newly complex functions.
3. Expand pipeline tests for missing owner artifacts or data lake, stale cross-market snapshots, and empty results from premium TuShare APIs.
4. Keep `a-share-daily` module boundaries clear: data access, charting, text rendering, and delivery should remain separate; do not put message-sending logic in the fetch stage.

Current boundaries:

1. `market-data-platform` remains a separate repository, accessed read-only through `DATA_PLATFORM_ROOT`.
2. Daily reports consume structured `items[]` with source, URL, and publication time; free-form news text does not go directly into the report body.
3. Hermes handles follow-up commentary and explanation. Code generates and delivers the factual report.
