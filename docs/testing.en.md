[Chinese version](testing.md)

# Testing and quality assurance

## Repository quality checks

```bash
uv sync --locked --group dev
uv run python project_tools/check_all.py --scope all
uv run pytest -k cli_pipeline --maxfail=1
uv run pytest -k contract
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest --cov --cov-report=term-missing
uv run python project_tools/package_coverage.py
uv run python project_tools/update_cli_help.py --check
```

`check_all.py` checks the `market-intel` root repository and its scripts. Three historical submodules have been retired; each owner repository runs its own checks. This repository must not scan adjacent directories to run tests on behalf of those owners.

`check_all.py` measures every Python production module under `src/`, including files that tests never import, and enforces a line-coverage floor for each package. Missing source files or a new package without a configured floor fail the gate. These baselines were measured on 2026-10-12 using the complete synthetic suite and locked dependencies. The existing five floors are unchanged; added packages have modest regression headroom. Commentary and publication coverage remain low: their initial floors prevent deterioration and do not establish sufficient behavioral validation.

| Production package | Measured baseline | Minimum |
| --- | ---: | ---: |
| `a_share_analysis` | 81.14% | 70% |
| `a_share_daily` | 76.82% | 65% |
| `daily_messenger` | 79.13% | 65% |
| `market_intel_commentary` | 15.11% | 10% |
| `market_intel_config` | 100.00% | 90% |
| `market_intel_publication` | 38.33% | 35% |
| `ops_common` | 64.27% | 50% |
| `research_contracts` | 79.74% | 70% |
| `style_replica_bridge` | 31.34% | 25% |
| `tushare_jobs` | 44.51% | 35% |

Coverage data defaults to `.coverage`. Set `COVERAGE_FILE` to store it outside the repository; the collector and package gate read the same file. Synthetic test outputs should also use an external temporary directory. Publication-boundary tests reject outputs inside the owner checkout or another source repository. If another `.git` marker affects the default temporary root, choose a fresh external test directory with `TMPDIR` or pytest `--basetemp`; preserve the marker and safety guard. Pytest clears the selected `--basetemp` directory, so never point it at existing data, source, or production directories.

Pull requests and pushes to `main` run `check_all.py --scope all --strict-tools`, build the Python package, and check the public boundary. GitHub Actions provides the complete quality result; the same gate can be run locally before submission.

Before deleting a merged branch, verify its pull-request state with the cleanup command. It is a dry run by default; pass `--yes` to delete:

```bash
uv run python project_tools/cleanup_merged_branches.py \
  --repo runchengxie/quant-intel-platform \
  --branch fix/example \
  --dry-run
uv run python project_tools/cleanup_merged_branches.py \
  --repo runchengxie/quant-intel-platform \
  --branch fix/example \
  --yes
```

GitHub Actions does not access live market data, Feishu, or brokerage services. Production data access and deployment checks must follow their separate runbooks. Production data scheduling belongs to Deploy and is outside this quality gate.

## Owner-boundary tests

Tests in this repository should focus on:

- ETL, theme scoring, market news, and fallback behavior
- Fail-closed validation of artifact dates, structure, and hashes
- Consumption of owner-produced DailyWatch20, D11-H5, and style-factor artifacts
- Report rendering, charts, dashboards, and audience isolation
- Feishu idempotency, delivery receipts, and failure recovery
- Scheduling and recovery logic that must not install or repair research-side timers
- Deploy's `refresh_daily_watch20.sh` restoring official artifacts only through the installed `daily-watch20-owner` CLI; Deploy owns those script tests

Algorithm tests for minute factors, Hermite, rolling training, OOS, ablation, AI ranking, and shadow runs belong to `quant-research`; `market-intel` does not duplicate them.

## Deployment and scheduler validation

Hermes, systemd, and Windows Task Scheduler scripts, templates, and host smoke procedures belong to private `quant-intel-deploy`. `ensure_hermes_gateway.sh`, `setup_cron.sh`, and `scripts/windows/test_scheduled_tasks.ps1` are not supplied here and are not this repository's test commands.

This repository validates public CLIs, artifact contracts, and offline fixtures. Host checks, one-off scheduled tasks, and real delivery validation follow Deploy's runbooks and separate authorization. Do not change the host clock or stop production services to test them.

## Core test categories

| Area | Focus |
| --- | --- |
| ETL / feeds | RSS and API parsing, retries, simulation, and fallback |
| scoring / digest | Theme scores, recommendations, rendering, and snapshots |
| contracts | JSON, artifact, and receipt fields and date constraints |
| A-share reports | Morning/evening structure, chart paths, stale-chart protection, and missing-data boundaries |
| DailyWatch20 consumer | Official-artifact validation, raw completeness, and delivery receipts |
| delivery | `lark-cli`/webhook, audience isolation, and idempotency |
| recovery | Freshness DAG, retry budgets, windows, and owner boundaries |
| Dashboard | Payloads, status panels, and HTML output |
| TuShare compatibility | Report-side export, storage, and window handling |

Use the current `uv run pytest` output for test counts; do not hard-code a count in documentation.

## Quality requirements

- Ruff lint and formatting pass
- `ty check` covers the root project's `src/`
- `pytest` and contract tests pass
- CLI help and `docs/cli-reference.md` are synchronized
- Shell, PowerShell, and JavaScript scripts pass static checks where tools are available
- For cross-repository features that depend on owner changes, record the provider pull request and corresponding owner commit before integration

Pull requests created through the GitHub connector cannot replace local `uv`, systemd, or live-provider validation. Large boundary migrations should remain Draft until the required local quality gates and deployment smoke tests have real results.
