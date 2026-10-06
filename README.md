# quant-intel-platform

The repository was formerly named `market-intel`. Current documentation uses `quant-intel-platform`; the Python distribution name, publication consumer ID `market-intel`, module names, and existing configuration/environment identifiers remain compatibility interfaces.

`quant-intel-platform` provides automated market reports, publication contracts, and information delivery. It collects market and news information, consumes versioned research artifacts from owner projects, then validates, organizes, and delivers the reviewed results. The separate `quant-intel-pages` repository renders and hosts public reports.

[中文 README](README.zh-CN.md) · [English language policy](docs/LANGUAGE_POLICY.md) · [中文语言政策](docs/LANGUAGE_POLICY.zh-CN.md)

[Market reports](https://runchengxie.github.io/quant-intel-pages/) · [Documentation](https://runchengxie.github.io/quant-intel-platform/docs/)

Strategy research and backtesting remain in their owner repositories. This project does not copy those implementations.

## Quick start

Requirements: Python 3.11 through 3.13 and `uv`.

```bash
uv sync --locked --no-dev
uv run dm --help
```

Start with the [getting started guide](docs/getting-started.md). Global market reports can be tried independently. A-share production research artifacts, data-lake access, and production scheduling require the relevant owner projects and permissions. See the [cross-project boundary](docs/boundary-contract.md).

## What this project provides

- Market daily reports, A-share morning and evening reports, and style-factor weekly reports.
- Validated public report snapshots and versioned consumer contracts.
- Daily US and Asian market snapshots with a five-report-date archive window.
- Configured report delivery with audience isolation and delivery receipts.

## Documentation

- [Getting started](docs/getting-started.md)
- [New-machine setup](docs/new-machine-setup.md)
- [System architecture](docs/architecture.md)
- [Market site](docs/how-to/market-site.md)
- [Operations](docs/operations.md)
- [Documentation index](docs/index.md)

Reports and analysis organize market information and do not constitute investment advice.
