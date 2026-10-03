[Chinese version](data-fetch-architecture.zh-CN.md)

# Cross-market data and report architecture

This page describes the cross-market data path used by `quant-intel-platform`. Production schedules, credentials, service units, and delivery targets are managed in the private `quant-intel-deploy` repository. This public repository contains reusable fetch, validation, report, and site code; its GitHub Actions workflows run quality checks and build the public site.

## Cross-market snapshot flow

The morning report obtains cross-market inputs through `src/a_share_daily/cross_market.py`:

1. Look for an exact-date snapshot under `data-snapshots/cross-market/`, then try `data-snapshots/latest/cross_market_snapshot.json`. Set `CROSS_MARKET_SNAPSHOT_ROOT` to use a stable external snapshot directory.
2. Accept only a snapshot that is not from a future date and is within the configured freshness window. Stale macro and sentiment observations are reported as freshness warnings.
3. If there is no usable snapshot, fetch the available inputs live. `CROSS_MARKET_FORCE_LIVE=1` skips the snapshot lookup.
4. Return partial results and record per-source errors so a failed optional source does not stop the rest of the report.

`src/a_share_daily/fallback_fetch.py` exposes the same snapshot-first behavior for an explicit date and can persist live results for later consumers. Production callers must use the stable data path configured by the deployment environment; scheduled jobs must not write to a temporary worktree.

Inputs include US and Asian market quotes, commodities, macro series, and sentiment sources. The Korean pre-market and overnight fields use an optional provider chain; without intraday data they remain daily-bar proxies. Each output retains its source and degradation information where the contract provides those fields.

## Report and website boundaries

The report pipeline consumes the cross-market result as one input to its dated report manifest. Freshness warnings and source errors remain visible to report generation. Cross-market data is informational and does not produce trading instructions.

The public website is built from reviewed, checked-in or uploaded artifacts. The `public-site` workflow builds the site and documentation; it does not run the production market-data schedule. The `public-quality` workflow runs repository checks. Real credentials, scheduled jobs, runtime state, and report delivery are owned by `quant-intel-deploy`.

## Key implementation paths

| Path | Responsibility |
| --- | --- |
| `src/a_share_daily/cross_market.py` | Snapshot selection, freshness checks, live cross-market fetch, and report input |
| `src/a_share_daily/fallback_fetch.py` | Snapshot-first fetch command and snapshot persistence |
| `src/a_share_daily/pipeline.py` | A-share report orchestration |
| `src/a_share_daily/morning_report.py` | Morning report assembly |
| `src/ops_common/paths.py` | Resolve operator-owned data and state paths |
| `src/ops_common/business_freshness.py` | Check cross-market snapshot freshness for recovery |
| `.github/workflows/public-quality.yml` | Public repository quality gate |
| `.github/workflows/public-site.yml` | Public site and documentation build, with Pages deployment from `main` |
| `quant-intel-deploy` | Private production configuration, schedules, secrets, runtime state, and delivery |

For production runbooks and schedule details, use the documentation in `quant-intel-deploy`. Do not infer the live schedule from the public site workflows.
