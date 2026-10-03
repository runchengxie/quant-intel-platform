# Frequently asked questions

[Chinese version](faq.md)

## Where should I start?

Read [Getting started in five minutes](getting-started.md), then [Core concepts](concepts.md). For a specific task, use the [common-task guides](how-to/run-daily-report.en.md).

## Can I run the project without API credentials?

Installation, help output, offline tests, documentation builds, and some fallback paths work without credentials. Live data retrieval requires the relevant provider credentials and access.

## Will a local run send messages?

Not by default. Delivery targets come from the deployment environment. With no target configured, the system generates local files only. Production delivery is managed by `quant-intel-deploy`.

## Why is the full A-share report missing?

The full A-share report requires formal inputs from the research and data repositories. When those inputs are unavailable, the platform shows available snapshots or explicitly marks missing states.

## What is the difference between `DATA_PLATFORM_ROOT` and `MDP_DIR`?

`DATA_PLATFORM_ROOT` points to the data directory. `MDP_DIR` points to the market-data repository's source tree and is used to invoke its public commands.

## How do I determine whether a run succeeded?

Inspect status files, generation time, and date under `out/`, then check for the corresponding receipt. Do not rely on the process exit code alone.

## May production configuration be committed here?

No. Production credentials, customer delivery targets, schedules, logs, receipts, and real snapshots belong in the private deployment environment. See [Public repository boundary](public-release/public-boundary.md).
