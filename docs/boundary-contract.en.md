# Cross-repository boundary contract

[Chinese version](boundary-contract.md)

This page supplements [Data ownership](data-ownership.en.md) and [Artifact contracts](contracts.md). It closes the source-code and filesystem-path coupling boundary. The 2026-07-29 integration review concluded that the repositories should remain independent and coordinate only through public CLIs and versioned file contracts; repository paths are not a supported interface.

## General rules

- `quant-intel-platform`, `quant-research`, `quant-platform`, and `quant-market-data-platform` are independent systems with different responsibilities. Research prioritizes version locking, reproducibility, and auditability; intelligence prioritizes daily scheduling, live retrieval, and delivery timeliness.
- Do not import another repository's business source code. Cross-repository communication uses public installed commands such as `marketdata ...`, `strategy ...`, `daily-watch20-owner ...`, and `marketops ...`, or versioned file artifacts such as `watchlist_20`, `selection_receipt`, `signals.parquet`, and `news_heat` (see `contracts.md`). Retired AI-selection products do not become production defaults through a legacy CLI or artifact name.
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

Production bridge scripts, Windows launchers, and scheduler templates belong to `quant-intel-deploy`, not this repository. Its `scripts/refresh_daily_watch20.sh` invokes the installed `daily-watch20-owner run/freshness` interface through the explicitly configured `QUANT_RESEARCH_ROOT`; market-data recovery uses the installed `marketdata` CLI at `MDP_DIR`. Its `installed_owner` helper clears `PYTHONPATH` and `PYTHONHOME` before invoking the installed executable. Report generation and delivery consume owner artifacts rather than importing sibling source trees.

Provider jobs in Deploy use `marketdata config run --config "$DATA_PLATFORM_CONFIG" -- COMMAND ARGS...` to load owner-managed supplier credentials. They do not source provider JSON or use provider `.env.local` as the canonical credential store. Other credential owners retain their configuration.

### Python source

`src/a_share_daily/deploy_check.py` and `tushare_credentials.py` accept only explicit `MDP_DIR`. `src/a_share_daily/daily_watch20_raw_completeness.py` owns DailyWatch20 minute-data completeness checks. Factor, Hermite, walk-forward, OOS, and ablation implementations belong to `quant-research`. Deployment scheduler configuration is maintained in `quant-intel-deploy`.

Repository scans and focused tests enforce these boundaries. Development-machine directory layout is not a deployment contract.

## Remove duplicate implementations

Responsibilities are assigned as follows:

- Private factor definitions and strategy calculations: `quant-research`.
- Reusable backtesting, execution simulation, and attribution: `quant-platform`.
- Generic backtest job state, workers, and result publication: `quant-backtest-runtime`.
- Strategy orchestration and artifact publication: `quant-research`.
- Report rendering and Feishu delivery: `quant-intel-platform`.

The old repository names describe migration history. Existing Python namespaces, CLI names, configuration keys, and artifact identifiers remain compatible interfaces, not independent current owners.

### Style-analysis migration

The duplicated `src/a_share_analysis/style/` package, including `data.py`, `attribution.py`, `factor_calc.py`, `factor_backtest.py`, `charts.py`, and `report.py`, was removed on 2026-07-30. It was a frozen copy of `research-workspace/src/style_factors` and had only test references; its removal did not affect production code.

`src/a_share_analysis/style_analysis.py` remains as the consumer adapter. It reads `$DATA_PLATFORM_ROOT/strategy_outputs/style-factors/latest.txt`, validates `ArtifactEnvelopeV2`, SHA-256, file size, and lineage through `research_contracts`, then copies the owner artifact and writes `consumption_receipt.json`. The `research_contracts` compatibility package is included in this distribution; `pyproject.toml` does not declare a separate Git-pinned `research-contracts` dependency.

### `tushare_jobs` migration

Overlapping downloads were reduced to compatibility exporters:

- `stock_st.py` reads MDP `stock_st` and exports the requested dates; it no longer calls TuShare.
- `listed_company.py` reads MDP `stock_company`, `stk_managers`, and `share_float`. Only the report-specific lightweight `stock_basic` snapshot may still be refreshed directly.
- `index_weight.py` exports paired MDP `index_weight`/`index_weight_daily` data; it no longer downloads or expands the series locally.
- `lightweight_snapshot.py` and cross-market snapshots remain because the platform has no equivalent lightweight JSON contract.

On 2026-07-30, MDP completed the equivalent retrieval capability for `stock_st`, `index_weight`, `index_weight_daily`, `stock_company`, `stk_managers`, and `share_float`, including `DatasetSpec`, download, `drift_weight` expansion, publication, CLI registration, registry, and asset paths. MDP is the authoritative owner. `quant-intel-platform` consumes `<DATA_PLATFORM_ROOT>/assets/tushare/a_share/<dataset>/a_share_all_<dataset>_latest.parquet` and the matching `.receipt.json`.

These consumers use fail-closed validation. Missing assets/receipts, schema mismatch, SHA-256 mismatch, row-count mismatch, or a missing requested slice cause an explicit failure; they do not fall back to direct TuShare retrieval. `force_full_refresh` also directs operators to MDP's public CLI. Consistency scripts may audit historical compatibility files but no longer control fallback behavior.

## Owner JSON configuration

Provider jobs launch through the installed, merged owner CLI:
`marketdata config run --config "$DATA_PLATFORM_CONFIG" -- COMMAND ARGS...`.
The selected versioned private JSON follows the data owner's contract. Version 1
can hold supplier credentials directly; version 2 references the owner-managed
credential registry and a separate job JSON. This consumer neither imports the
owner's loader nor parses supplier JSON. Doctor helpers inspect selected-file
metadata and inherited credential status only. With JSON selected, legacy
provider env files and provider entries in project env files are excluded;
other credential owners retain their configuration. Use the pinned owner's
`config check` for JSON validation and run doctor through `config run`.
