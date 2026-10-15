[Chinese version](maintenance-scripts.md)

# Maintenance scripts and experiment-code boundaries

This repository exposes production CLIs, local diagnostics, and research tools. Deployment schedules, production bridge scripts, and recovery entry points are maintained in `quant-intel-deploy`.

## Production entry points

| Entry point | Purpose | Scheduling / quality gate | Quality requirements |
| --- | --- | --- | --- |
| `dm` | Daily-report ETL, scoring, rendering, and BTC helper commands | Local report jobs; PR/main CI | Ruff, formatting, ty, pytest with coverage, and contract tests |
| `marketops` | TuShare data jobs | Deployment-managed schedules invoke the installed CLI; PR/main CI | Ruff, formatting, ty, and TuShare unit tests |
| `a-share-daily` | A-share morning/evening reports, charts, and Feishu factual-layer delivery | Deployment-managed Task Scheduler, systemd, cron, or Hermes jobs invoke the installed CLI | Ruff, ty, and focused pytest coverage; ty covers all `src/` code |

## Low-frequency operations commands

| Command | Purpose | Notes |
| --- | --- | --- |
| `dm btc init-history` | Download Binance historical candles and consolidate Parquet | Higher network and disk use; check `out/btc/` or the configured output directory first |
| `marketops tushare stock-st backfill` | Backfill historical ST data | Uses TuShare quota; specify a date range where possible |
| `marketops tushare listed-company backfill --consolidate` | Refresh all listed-company data | Uses TuShare quota; check resumability and output format |

## Deployment-owned scripts and schedules

`quant-intel-deploy` owns production shell and PowerShell bridges, Task Scheduler/systemd/cron/Hermes definitions, freshness watchdogs, and recovery commands. Those files are not part of this repository. They call the installed `marketops` and `a-share-daily` CLIs or consume versioned owner artifacts. The public application and its tests remain in this repository.

## `project_tools/`

| Script | Users | Called by CI | Purpose |
| --- | --- | --- | --- |
| `check_all.py` | Developers, GitHub Actions | Yes, full quality gate | Runs Python, shell, PowerShell, and JavaScript checks |
| `update_cli_help.py` | Developers, GitHub Actions | Yes, called by the full gate | Detects drift in CLI documentation |

Register new scripts in the relevant table and document whether they are called by CI or production schedules, which environment variables or secrets they require, whether they access the network/use quotas/write large files, and whether failure blocks release.

## Compatibility entry points and legacy inventory

| Entry point | Status | Owner | Handling |
| --- | --- | --- | --- |
| `src/ops_common/notify_email.py` | No current call sites | `marketops` operations | No repository references remain. Before re-enabling email alerts, add tests and documentation; otherwise it can be removed in a later cleanup |

`src/a_share_analysis/post_market_review.py` was a post-market commentary compatibility wrapper. Its canonical implementation moved to `a_share_daily.review`; schedulers use `a-share-daily evening/review`. The unused wrapper has been deleted.

## A-share daily CLI: `a_share_daily`

`src/a_share_daily/` owns production morning/evening report generation, chart output, and delivery of the factual layer through Feishu. It depends on local `DATA_PLATFORM_ROOT`, owner public CLIs/artifacts, and `data-snapshots/`. Existing tests cover delivery, news contracts, CLI smoke behavior, missing-data boundaries, and deployment checks.

Implemented capabilities:

1. `a-share-daily doctor` checks script permissions, the `market-data-platform` repository, data lake, latest snapshots, AI key, Feishu destinations, and `lark-cli`. With `--live`, it also checks Task Scheduler on Windows or systemd timers on Linux, plus Hermes schedules.
2. Deployment-owned refresh jobs may request supplemental theme, money-flow, concept, and limit-move data. These APIs are disabled by default and require `A_SHARE_ENABLE_TUSHARE_PREMIUM=1`. Candidate pools, research computation, and official DailyWatch20 artifacts belong to `quant-research` / `strategy-pipeline`; this repository validates, renders, and delivers published artifacts only.
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
