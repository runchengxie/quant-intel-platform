[Chinese version](daily-schedule.md)

# Market Intel daily schedule

This page covers reports, delivery, data preparation, and recovery owned by `market-intel`. Research algorithms, factor experiments, ablations, and strategy production belong to `quant-research` and `quant-platform`. This repository restores official artifacts only through public CLIs when needed.

Production schedules and bridge scripts are maintained in `quant-intel-deploy`. The table describes tracked timer definitions and intended workflow; it does not establish which timers are enabled on a host. Bridge-script commands must be run from a `quant-intel-deploy` checkout, not this repository.

## Operating principles

1. Reports consume published artifacts that pass date, hash, and schema checks.
2. `market-intel` does not duplicate research models or use retired submodules to produce candidate pools or AI rankings.
3. DailyWatch20 strategy logic belongs to `quant-research` (`strategy_app.daily_watch20`). The producer bridge calls its installed owner CLI and does not implement strategy logic.
4. Refresh data required by the day's evening report before 19:00. Later jobs are for backfills, the next morning report, or freshness repair.
5. A systemd timer outside the Gateway handles Gateway recovery.
6. Freshness is based on business dates and artifact receipts, not process exit codes alone.
7. Automatic recovery has attempt and cooldown budgets. Validate before delivery; if a successful send exists but its receipt is not aligned, do not resend.
8. Research-side factor observation, DailyWatch20 ablation, standalone hot-sector jobs, and the legacy AI freshness timer have been retired from this repository.

## Linux / Hermes schedule

| Time | Entry point | Owner | Purpose |
| --- | --- | --- | --- |
| Weekdays 05:20 | `daily-watch20-producer.timer` → `refresh_daily_watch20_quant_research.sh` | Deploy bridge → quant-research | Preflight the exact-date all-market artifact with `daily-watch20-owner freshness` and exit if it already passes; otherwise run `daily-watch20-runtime` with the configured data root and minute overlays to publish |
| 06:00 / 06:45 | `local-fetch-cross-market.timer` | market-intel | Refresh cross-market snapshots; the second run retries later-updating sources |
| Weekdays 06:40 | `a-share-morning-product-supervisor-preflight.timer` | market-intel | Check official DailyWatch20/D11-H5 artifacts and same-day recovery conditions |
| Weekdays 06:50 | `hermes-gateway-preflight.timer` | market-intel | Start and recheck an inactive Gateway; no-op when healthy |
| Weekdays 07:00 | Hermes `morning_pipeline.sh` | market-intel | Validate and deliver DailyWatch20, D11-H5, and the morning report; do not run the legacy AI picker |
| Weekdays 07:15 | `a-share-morning-product-supervisor-postflight.timer` | market-intel | Check artifact hashes, delivery receipts, and idempotent resend conditions |
| 17:30 | `asia-market-refresh.timer` | Data bridge | Fetch or consume A-share daily data and Asia close data for the evening report |
| 18:00 | `a-share-current-publish.timer` | Data bridge | Build and validate the A-share current contract and report inputs |
| 18:20 / 18:40 | `a-share-report-datasets-refresh.timer` | market-data-platform producer | Prepare TuShare evening-report data and write dated receipts |
| Weekdays 18:50 | `hermes-gateway-preflight.timer` | market-intel | Check the Gateway before the evening report |
| Weekdays 19:00 | Hermes `evening_pipeline.sh` | market-intel | Deliver the Asia post-close / US pre-market report |
| 19:20 / 20:30 | `a-share-report-datasets-refresh.timer` | market-data-platform producer | Backfill evening data and repair next-day freshness |
| Saturdays 08:15 | `a-share-style-factor-weekly-refresh.timer` | quant-research producer bridge | Call the standard publisher; factor calculation is not implemented here |
| Saturdays 09:00 | Hermes `weekly_recap.sh` | market-intel | Consume published weekly research outputs and deliver a recap |
| About 5 minutes after boot, then every 45 minutes | `market-intel-scheduled-recovery.timer` | market-intel | Check data, report inputs, official strategy artifacts, and delivery state; run bounded allowlisted recovery |

## Retired tasks

`market-intel` no longer installs, schedules, or automatically recovers `a-share-factor-observation-refresh.timer`, `daily-watch20-ablation.timer`, `hotsector-research-handoff.timer`, `a-share-ai-stock-picker-freshness.timer`, or scheduled jobs from the three historical owner submodules. `quant-intel-deploy/scripts/setup_cron.sh --layer2` disables and removes these old user-unit files. Research jobs belong in their owner repositories.

## DailyWatch20 production boundary

```text
market-data-platform data / report inputs
        ↓
quant-intel-deploy: refresh_daily_watch20_quant_research.sh
        ↓
quant-research: daily-watch20-owner freshness preflight → run daily-watch20-runtime only when needed
        ↓
versioned DailyWatch20 artifact + selection_receipt
        ↓
quant-intel-deploy bridge + quant-intel-platform: validate → render → delivery_receipt → Feishu
```

`refresh_daily_watch20_quant_research.sh` receives its minute-quota settings and data paths from Deploy. The systemd service controls bounded retries, and the 06:40 morning supervisor checks same-day recovery conditions. This bridge does not backfill minute data or implement candidate-pool algorithms, model training, Hermite research, or ablation. News heat is optional: the owner runtime consumes the requested-date artifact when available; this bridge does not build it or launch the retired `hot-sector-screener` producer.

## Delivery windows and recovery

Hermes restarts can collapse missed recurring runs, so scripts check their delivery windows first:

- Morning: approximately 06:30–09:15; evening: approximately 17:30–23:30.
- Outside these windows, an audit artifact may be generated, but external delivery is disabled.
- If a successful send is evidenced for the business date but its receipt is not aligned, recovery records `delivery_unverified` and does not resend.

The window is determined by `ops_common.report_window` and the official delivery receipt.

Critical systemd timers with `Persistent=true` trigger recently missed jobs after restart. They do not replay every historical schedule or retry a failed one-shot indefinitely. The recovery timer evaluates a business-date freshness DAG: core data/current contract, report enhancements/cross-market inputs, official DailyWatch20, and morning/evening delivery receipts. Research factor pipelines are excluded, so a missing report does not start a research experiment.

Deployments can pass `--disable-stage <stage>`. Downstream dependencies are marked `disabled_dependency` and are not probed, rerun, or alerted on. Disabling `morning_model`, for example, also skips its dependent `morning_report`. Per-stage retry counts are bounded and stored in `state/scheduled_recovery/<YYYYMMDD>.json`; `latest.json` and the heartbeat record current state. Failure alerts are deduplicated by fingerprint.

For `report_datasets`, recovery verifies the owner's `a_share_evening_data_<YYYYMMDD>.json` receipt: it must target the requested date, show premium enabled, mark all three required enhancement datasets `ready`, and have their partition files present. The legacy `a_share_report_dataset_refresh_<YYYYMMDD>.json` receipt is used only when the owner receipt is absent; it cannot mask a failed owner receipt. If financing-balance data in the public six-chart dashboard trails the trading-volume series by more than one previous trading day, the dashboard is `degraded` and preserves each point's observation date.

## Manual recovery

Run the bridge commands below from a `quant-intel-deploy` checkout. They are deployment operations, not scripts shipped by this repository.

```bash
bash scripts/refresh_tushare_daily.sh YYYYMMDD
bash scripts/publish_a_share_current.sh YYYYMMDD
A_SHARE_ENABLE_TUSHARE_PREMIUM=1 bash scripts/refresh_tushare_report_datasets.sh YYYYMMDD
```

Restore an official DailyWatch20 artifact:

```bash
WATCHLIST20_SOURCE_DATE=YYYYMMDD WATCHLIST20_SIGNAL_DATE=YYYYMMDD \
  bash scripts/refresh_daily_watch20_quant_research.sh
```

This bridge can publish a production artifact. Run it only for an explicitly authorized recovery; installation of the owner CLI alone does not authorize resuming a paused strategy.

Validate or deliver an already published artifact:

```bash
uv run python scripts/send_daily_watch20.py \
  --date YYYYMMDD \
  --signal-date YYYYMMDD \
  --dry-run
```

Do not run retired `run_daily_watch20_ablation.sh`, `refresh_a_share_factor_observation.sh`, or legacy AI-picker/hot-sector production entry points.

## Deployment

Run the deployment commands below from a `quant-intel-deploy` checkout. They install or inspect deployment-owned jobs and call the installed public CLI.

```bash
export DATA_PLATFORM_ROOT=/path/to/data/market-data-platform
export MDP_DIR=/path/to/quant-market-data-platform
export QUANT_RESEARCH_ROOT=/path/to/quant-research
bash scripts/setup_cron.sh --layer2
bash scripts/setup_cron.sh --layer3
uv run a-share-daily doctor --live
```

Inspect installed jobs with:

```bash
systemctl --user list-timers --all | rg 'hermes-gateway|scheduled-recovery|a-share|cross|asia|daily-watch20'
systemctl --user status hermes-gateway-preflight.timer
systemctl --user status market-intel-scheduled-recovery.timer
systemctl --user status daily-watch20-producer.timer
hermes cron list
```

Use `quant-research` / `strategy-research` documentation for research schedules and experiment cadence.
