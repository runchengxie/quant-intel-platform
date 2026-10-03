# Cross-repository boundary contract

[Chinese version](boundary-contract.md)

This page supplements [Data ownership](data-ownership.en.md) and [Artifact contracts](contracts.md). It closes the source-code and filesystem-path coupling boundary. The 2026-07-29 integration review concluded that the repositories should remain independent and coordinate only through public CLIs and versioned file contracts; repository paths are not a supported interface.

## General rules

- `market-intel`, `quant-research`, `quant-platform`, and `market-data-platform` are independent systems with different responsibilities. Research prioritizes version locking, reproducibility, and auditability; intelligence prioritizes daily scheduling, live retrieval, and delivery timeliness.
- Do not import another repository's business source code. Cross-repository communication uses public installed commands such as `marketdata ...`, `strategy ...`, `marketops ...`, and `aipick ...`, or versioned file artifacts such as `watchlist_20`, `selection_receipt`, `signals.parquet`, and `news_heat` (see `contracts.md`).
- Repository paths are not APIs. Scripts and modules must not depend on another checkout's fixed directory layout, including paths tied to one developer's machine.

## Path-coupling rules

Use explicit deployment environment variables and public CLIs instead of hard-coded paths:

| Disallowed pattern | Required pattern |
| --- | --- |
| A developer-machine checkout path | Read `DATA_PLATFORM_ROOT` for the data lake or `MDP_DIR` for the source checkout; deployment sets both explicitly |
| `cd "$QUANT_RESEARCH_ROOT" && uv run strategy ...` | `uv run --project "$QUANT_RESEARCH_ROOT" strategy ...` without changing the working directory |
| Falling back to a fixed `$HOME/code/...` path | Do not provide an implicit fallback; fail with an actionable error and require deployment configuration |

`src/ops_common/env.py::_env_paths_to_try()` no longer appends a fixed checkout as an implicit `.env` search root. It adds an alternate root only when `MDP_FALLBACK_ROOT` is explicitly set; the formal data interface is `DATA_PLATFORM_ROOT`. An unconfigured deployment now fails rather than relying on a developer's filesystem.

### Scripts and service managers

The following scripts no longer default `MDP_DIR` to a local path: morning/evening pipelines, publication, TuShare refresh, weekly recap, morning-product supervisor, and report-dataset refresh. They require `MDP_DIR` and consistently reference `.env.local` beneath that checkout.

`scripts/refresh_daily_watch20.sh` invokes the public producer CLI using only `QUANT_RESEARCH_ROOT` and `MDP_DIR`. If news heat is missing, it continues without rebuilding it in this repository. `scripts/daily_watch20_delivery.sh` validates the DailyWatch20 artifact produced by `strategy-pipeline`, then calls local rendering/delivery entry points. The former `scripts/hotsector_research_handoff.sh` and `scripts/send_hotsector_client_preview.py` compatibility shells were removed from `quant-intel-deploy` in 2026-10. Current callers use the DailyWatch20 delivery commands directly; old paths in the migration manifest are provenance only.

`scripts/windows/common.ps1` no longer supplies a default `MDP_DIR`; it derives an allowed value or fails. `scripts/setup_cron.sh` writes `DATA_PLATFORM_ROOT`, `MDP_DIR`, and `QUANT_RESEARCH_ROOT` to a deployment environment file with mode `0600`. systemd loads it using `EnvironmentFile=`; Hermes entry points source the same deployment configuration before boundary checks. Services that depend on cross-repository paths, including the DailyWatch20 producer, morning supervisor, and TuShare refresh, load this file rather than defining their own defaults.

### Python source

`src/a_share_daily/deploy_check.py` and `tushare_credentials.py` accept only explicit `MDP_DIR`. `src/a_share_daily/daily_watch20_raw_completeness.py` owns DailyWatch20 minute-data completeness checks. Factor, Hermite, walk-forward, OOS, and ablation implementations belong to `quant-research`. `scripts/setup_cron.sh` requires explicit `MDP_DIR` and `QUANT_RESEARCH_ROOT`; it does not use developer-specific defaults.

Repository scans and focused tests enforce these boundaries. Development-machine directory layout is not a deployment contract.

## Remove duplicate implementations

Responsibilities are assigned as follows:

- Factor definitions and calculations: `alpha-research`.
- Backtesting and attribution: `portfolio-backtester`.
- Strategy execution and artifact publication: `strategy-pipeline`.
- Report rendering and Feishu delivery: `market-intel`.

### Style-analysis migration

The duplicated `src/a_share_analysis/style/` package, including `data.py`, `attribution.py`, `factor_calc.py`, `factor_backtest.py`, `charts.py`, and `report.py`, was removed on 2026-07-30. It was a frozen copy of `research-workspace/src/style_factors` and had only test references; its removal did not affect production code.

`src/a_share_analysis/style_analysis.py` remains as the consumer adapter. It reads `$DATA_PLATFORM_ROOT/strategy_outputs/style-factors/latest.txt`, validates `ArtifactEnvelopeV2`, SHA-256, file size, and lineage through `research_contracts`, then copies the owner artifact and writes `consumption_receipt.json`. The installed dependency pins `research-contracts` to an explicit Git commit; the validation implementation is no longer duplicated here.

### `tushare_jobs` migration

Overlapping downloads were reduced to compatibility exporters:

- `stock_st.py` reads MDP `stock_st` and exports the requested dates; it no longer calls TuShare.
- `listed_company.py` reads MDP `stock_company`, `stk_managers`, and `share_float`. Only the report-specific lightweight `stock_basic` snapshot may still be refreshed directly.
- `index_weight.py` exports paired MDP `index_weight`/`index_weight_daily` data; it no longer downloads or expands the series locally.
- `lightweight_snapshot.py` and cross-market snapshots remain because the platform has no equivalent lightweight JSON contract.

On 2026-07-30, MDP completed the equivalent retrieval capability for `stock_st`, `index_weight`, `index_weight_daily`, `stock_company`, `stk_managers`, and `share_float`, including `DatasetSpec`, download, `drift_weight` expansion, publication, CLI registration, registry, and asset paths. MDP is the authoritative owner. `market-intel` consumes `<DATA_PLATFORM_ROOT>/assets/tushare/a_share/<dataset>/a_share_all_<dataset>_latest.parquet` and the matching `.receipt.json`.

These consumers use fail-closed validation. Missing assets/receipts, schema mismatch, SHA-256 mismatch, row-count mismatch, or a missing requested slice cause an explicit failure; they do not fall back to direct TuShare retrieval. `force_full_refresh` also directs operators to MDP's public CLI. Consistency scripts may audit historical compatibility files but no longer control fallback behavior.
