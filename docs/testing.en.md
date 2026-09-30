[中文页面](testing.md)

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

`check_all.py` collects coverage during the full test run and then checks each production package against its minimum line-coverage threshold. The current starting thresholds leave regression headroom below the measured local baselines:

| Production package | Current baseline | Minimum |
| --- | ---: | ---: |
| `a_share_analysis` | 81.14% | 70% |
| `a_share_daily` | 75.82% | 65% |
| `daily_messenger` | 76.90% | 65% |
| `ops_common` | 58.47% | 50% |
| `tushare_jobs` | 44.51% | 35% |

Pull requests and pushes to `main` run `check_all.py --scope all --strict-tools`, build the Python package, and check the public boundary. GitHub Actions provides the complete quality result; the same gate can be run locally before submission.

Before deleting a merged branch, verify its pull-request state with the cleanup command. It is a dry run by default; pass `--yes` to delete:

```bash
uv run python project_tools/cleanup_merged_branches.py \
  --repo runchengxie/market-intel \
  --branch fix/example \
  --dry-run
uv run python project_tools/cleanup_merged_branches.py \
  --repo runchengxie/market-intel \
  --branch fix/example \
  --yes
```

GitHub Actions does not access live market data, Feishu, or brokerage services. Production data access and deployment checks must follow their separate runbooks. This policy does not apply to pure data workflows.

## Owner-boundary tests

Tests in this repository should focus on:

- ETL, theme scoring, market news, and fallback behavior
- Fail-closed validation of artifact dates, structure, and hashes
- Consumption of owner-produced DailyWatch20, D11-H5, and style-factor artifacts
- Report rendering, charts, dashboards, and audience isolation
- Feishu idempotency, delivery receipts, and failure recovery
- Scheduling and recovery logic that must not install or repair research-side timers
- `refresh_daily_watch20.sh` restoring official artifacts only through the public `strategy-pipeline` CLI

Algorithm tests for minute factors, Hermite, rolling training, OOS, ablation, AI ranking, and shadow runs belong to `quant-research`; `market-intel` does not duplicate them.

## Linux and Hermes operations tests

Use a fake `systemctl` or static shell checks for the Gateway daemon and systemd templates. Tests must not stop the production Gateway:

```bash
uv run pytest tests/test_hermes_gateway_preflight.py
bash -n scripts/ensure_hermes_gateway.sh scripts/setup_cron.sh
```

After deployment, use read-only checks:

```bash
systemctl --user status hermes-gateway.service
systemctl --user status hermes-gateway-preflight.timer
systemctl --user list-timers --all
journalctl --user -u hermes-gateway-preflight.service --since today
```

Production schedulers, host installation, and cleanup of historical research-only units belong to the private `deploy` repository. Tests here cover only the public CLI, contracts, and offline fixtures.

## Windows scheduling smoke test

Do not change the host clock to test Task Scheduler. Use an isolated one-off task:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\windows\test_scheduled_tasks.ps1 `
  -Kind morning `
  -DelayMinutes 2 `
  -Delivery none `
  -SkipAiNews `
  -SkipPremiumRefresh
```

The default does not send messages to real recipients and writes artifacts to an isolated directory. Testing real delivery requires explicitly enabling it and using a temporary dedicated destination.

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
