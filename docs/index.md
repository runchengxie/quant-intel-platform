# Quant Market Intel

[Chinese version](index.zh-CN.md)

Quant Market Intel is the public framework for market intelligence, reporting, and published research contracts. The daily reports are rendered and hosted by [Quant Market Intel Pages](https://runchengxie.github.io/quant-intel-pages/). Start with the [five-minute setup](getting-started.md), then read the [core concepts](concepts.md) and [system architecture](architecture.md).

Production credentials, scheduled jobs, real delivery targets, and runtime state belong to the private deployment repository. This public repository provides reusable code, versioned contracts, offline checks, and reviewed public pages.

The published reports show facts with source dates, evidence links, and explicit data-quality boundaries. Research algorithms and strategy artifacts remain owned by `quant-research`, `quant-platform`, `strategy-pipeline`, and the other owner repositories documented in the boundary contracts.

## Choose a task

1. **Read the reports** with [Quant Market Intel Pages](https://runchengxie.github.io/quant-intel-pages/).
2. **Run the framework** with [Getting started](getting-started.md) and [Run a daily report](how-to/run-daily-report.en.md).
3. **Check the evidence** using [Core concepts](concepts.md), [Data contracts](contracts.md), and [Data provenance](public-release/data-provenance.en.md).
4. **Maintain the system** using [Architecture](architecture.md), [Operations](operations.md), and [Testing](testing.en.md).

## Documentation scope

| Area | Purpose |
| --- | --- |
| Global market reports | Collect market and news inputs, produce reports and dashboards |
| A-share analysis | Assemble market facts into morning and evening reports and charts |
| Research artifact consumption | Validate versioned artifacts published by their owning repositories |
| Data contracts | Define cross-module and cross-repository formats and receipts |

Start with the offline checks in Getting started. Producing and delivering live reports requires the configuration described in the operating guides.
