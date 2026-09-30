# Data ownership

[中文页面](data-ownership.md)

This project separates externally owned data products, lightweight report-specific snapshots, and code-generated reports. Hermes reads deterministic fact materials and provides subsequent commentary. Code generates the facts.

The daily-report framework is a code contract: Python and shell pipelines define required data, fallback behavior, report order, and delivery destinations. Agent responsibilities begin after the fact materials are produced; agents may interpret them, add sourced context, and answer follow-up questions.

## Principles

1. `market-data-platform` owns large, historical, and cross-strategy reusable data.
2. `market-intel` does not embed or vendor `market-data-platform` source code.
3. `market-intel` may retain lightweight, report-specific, persistent snapshots.
4. Code templates render the final morning/evening reports. Deterministic calculations produce evening status, contradictions, and validation conditions. LLM/search may only produce sourced candidate news.
5. News without provenance or a URL, or news that fails contract validation, must not enter code-generated reports.

## Data boundaries

| Data domain | Owner | Use in `market-intel` | Live retrieval allowed? |
| --- | --- | --- | --- |
| Full A-share daily data, money flow, concepts, margin data, indices, and historical backtest inputs | `market-data-platform` | Read-only access under `DATA_PLATFORM_ROOT/assets/tushare/a_share/` | No full-dataset retrieval during report generation |
| ETF rotation/hot-sector raw inputs | `market-data-platform` | Subprojects read from `DATA_PLATFORM_ROOT` | Must not write back to the data lake |
| DailyWatch20 candidate pool, strategy calculations, and formal artifacts | `quant-research` / `strategy-pipeline` | Read and validate through `WATCHLIST20_ROOT` | Owner publishes; `market-intel` does not recompute |
| Cross-market snapshots for US/Japan/Korea, commodities, macro, and sentiment | `market-intel` | `data-snapshots/cross-market/` and `latest/` | Fallback is allowed when a snapshot is missing, and the snapshot is refreshed |
| Lightweight TuShare snapshots | `market-intel` | `data-snapshots/tushare/` for backups and portable environments | Scheduled lightweight retrieval from GitHub Actions is allowed |
| GLM/Aliyun/Gemini market news | `market-intel` | Consume structured `items[]` with `title/source/url/published_at/summary` | Online search is allowed; invalid items are skipped |
| Morning/evening report text | `market-intel` | Python renderers produce Markdown and Feishu messages | Facts and deterministic interpretation come from code |

## `tushare_jobs` migration status

Some tasks under `src/tushare_jobs/` overlapped with the `market-data-platform` data lake. Ownership has been returned to the platform:

| Task | Platform equivalent | Current handling |
| --- | --- | --- |
| `stock_st.py` | Platform publishes `stock_st` | Read-only consume; validate the receipt before exporting a compatibility CSV |
| `listed_company.py` | Platform publishes `stock_company`, `stk_managers`, and `share_float` | Read-only consume; only the report-specific lightweight `stock_basic` snapshot remains a direct fetch |
| `index_weight.py` / `index_weight_daily.py` | Platform publishes raw and daily mirrors | Read-only consume; do not refetch or expand locally |
| `lightweight_snapshot.py` | No equivalent lightweight JSON in the platform | Retain as a report-specific offshore/backup snapshot |
| Report-enhancement mirrors (`mirror-a-share-*`) | Covered by MDP via `refresh_tushare_report_datasets.sh` | Migrated; no duplicate implementation remains |

Consumers of MDP-owned reference data validate receipt schema, dataset identity, SHA-256, and row count. A failed check exits explicitly; it does not fall back to the old downloader. See [Cross-repository boundary contract](boundary-contract.en.md).

The migration completed on 2026-07-30. `market-data-platform` owns the equivalent download capability for the six reference datasets through `providers/tushare_a_share_reference.py`, `marketdata tushare download-a-share-reference`, registry entries, and asset paths. `market-intel` reads published files under `<DATA_PLATFORM_ROOT>/assets/tushare/a_share/<dataset>/a_share_all_<dataset>_latest.parquet` and their receipts. The old duplicate-download paths are retired.

## Deployment conventions

`DATA_PLATFORM_ROOT` points to the data-lake root; `MDP_DIR` points to the market-data repository checkout. Deployment must set both explicitly:

```bash
export DATA_PLATFORM_ROOT=/path/to/data/market-data-platform
export MDP_DIR=/path/to/quant-market-data-platform
```

A new machine or server needs a runnable `market-intel` checkout, an `MDP_DIR` checkout for invoking the platform's public CLI, and a refreshed data directory at `DATA_PLATFORM_ROOT`.

Without the full data lake, morning reports may still use cross-market and lightweight TuShare snapshots from `data-snapshots/`. Full A-share analysis, hotspot screening, and charts will degrade or fail explicitly rather than rebuilding a full downloader inside `market-intel`. See [New-machine setup](new-machine-setup.en.md).

## Report-generation boundaries

Each run first creates auditable intermediate artifacts rather than assembling free-form text at delivery time:

- News: `ai_market_news*.json` (morning reports use an empty payload by default and do not call AI news retrieval).
- Morning manifest: `morning_manifest.json`.
- Evening manifest: `evening_manifest.json`.
- Evening review: `evening_review.json` and `evening_review.md`; `market_temperature` is a deterministic, auditable interpretation layer.
- Charts: `out/a_share_daily/*.png`.
- Public-chart candidate: `market_intel.a_share_charts.v1` JSON containing six allowlisted chart values, observation dates, provenance, and quality states. A candidate is not approved for publication.
- Daytime validation archive: `out/a_share_daily/history/evening_review_YYYYMMDD.json` and its Markdown/temperature chart.

Contracts and tests constrain these artifacts. Delivery consumes the files and does not ask an LLM to make new factual judgments. Public-chart candidates must stay outside the repository; never copy private manifests, PNG paths, or raw details to the public site. Public review and publication are handled separately by Pages and the deployment repository.

The offline export command does not fetch, send, or publish:

```bash
uv run a-share-daily chart-candidate \
  --manifest /external/reports/morning_manifest.json \
  --out /external/candidates/2026-09-18-morning.json \
  --date 20260918 --kind morning
```

The top-level candidate fields are `schema_version/publication/report_id/date/kind/generated_at/charts/content_sha256`; it contains exactly six cards. `publication` is always `candidate`. A downstream reviewer must independently validate each point's source, authorization, and date before creating a separate public artifact. Identical input, including fixed `generated_at`, produces the same SHA-256. Feishu targets, error text, and absolute PNG paths from the source manifest are never exported.

Observation dates come from the corresponding data partition or US close row, not the report-generation date. Weekly charts and dashboards retain each series point's own date. Money-flow data uses its older source partition; some US symbols lack verifiable points and are marked `degraded`. Missing data, a missing trustworthy observation date, or a missing source URL is marked `missing`; a placeholder PNG is not evidence. DailyWatch20 topic summaries currently lack publicly verifiable point-level URLs, so their public chart card remains missing rather than presenting an internal artifact path as a public source. The evening fourth chart is the six-dimension market thermometer, not the morning sentiment indicator; until its individual points can be reviewed, the evening candidate marks that card missing. Existing morning/evening PNGs and Feishu delivery are unaffected by this export command.

### Morning pipeline

Entry point: `scripts/morning_pipeline.sh`.

1. `daily_watch20_delivery.sh` validates and sends the `strategy-pipeline` DailyWatch20 artifact. Failure does not block later reports.
2. `a_share_daily.d11_h5_shadow_delivery` consumes only owner-published research artifacts. The old AI-picks entry remains an explicit manual compatibility call and is not part of default scheduling.
3. News JSON is empty by default. `fetch_ai_market_news.py` runs only when `MORNING_ENABLE_AI_NEWS=1`.
4. `a-share-daily morning` builds the deterministic manifest.
5. `a-share-daily morning-report` renders Markdown from the manifest, snapshots, and news `items[]`.
6. `morning_pipeline.sh` calls `a_share_daily.delivery.report_delivery` to deliver factual material (`lark-cli` primary, Hermes follow-up, webhook text fallback).
7. Hermes may comment on the same Markdown/manifest. Commentary failure does not block delivery of the factual material.

### Evening pipeline

Entry point: `scripts/evening_pipeline.sh`.

The evening workflow reuses code-generated `a-share-daily evening/review` outputs. The summary report renderer consumes structured facts and `market_temperature`. The temperature calculation does not access the network or call a model; it uses same-day aggregates, the previous 20-session turnover baseline, and validation conditions from the preceding archive. The commentary workflow must not rewrite facts in `evening_review.md`.

`evening_pipeline.sh` generates `evening_summary.md`, `evening_review.md`, and charts, replaces the old evening sentiment chart with the six-dimension thermometer, and archives the review for next-session validation. Code delivers the full report; Hermes provides follow-up commentary and explanation.
