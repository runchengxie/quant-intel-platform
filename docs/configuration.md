# Configuration

[中文页面](configuration.zh-CN.md)

Configuration has two layers: public safe defaults kept in this repository and runtime parameters supplied by the deployment environment.

## Public environment variables

Examples of non-secret deployment paths and target identifiers include:

```bash
MARKET_INTEL_CLIENT_CHAT_ID=example_client_target
MARKET_INTEL_INTERNAL_CHAT_ID=example_internal_target
MARKET_INTEL_PUBLIC_CHAT_ID=example_public_target
DATA_PLATFORM_ROOT=/path/to/local/data
A_SHARE_OUTPUT_DIR=/path/to/report/output
```

Production credentials and real delivery targets must be injected by the deployment environment. Do not commit tokens, private paths, raw data, receipts, or runtime state.

## Cross-repository roots

Use explicit paths when a workflow invokes an owner CLI:

```bash
DATA_PLATFORM_ROOT=/path/to/data/market-data-platform
MDP_DIR=/path/to/quant-market-data-platform
QUANT_RESEARCH_ROOT=/path/to/quant-research
MARKET_INTEL_ROOT=/path/to/quant-intel-platform
```

The repository path is only a process entry point, not a Python import boundary. Validate the resulting artifact and receipt after the owner CLI completes.
