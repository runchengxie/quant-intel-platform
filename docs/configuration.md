# Configuration

[Chinese version](configuration.zh-CN.md)

Configuration has two layers: public safe defaults kept in this repository and runtime parameters supplied by the deployment environment.

## Public environment variables

Examples of non-secret deployment paths and target identifiers include:

```bash
MARKET_INTEL_CLIENT_CHAT_ID=example_client_target
MARKET_INTEL_INTERNAL_CHAT_ID=example_internal_target
MARKET_INTEL_PUBLIC_CHAT_ID=example_public_target
DATA_PLATFORM_ROOT=/path/to/local/data
A_SHARE_OUTPUT_DIR=/path/to/report/output
A_SHARE_DELIVERY_STATE_DIR=/path/to/delivery/state
SCHEDULED_RECOVERY_STATE_ROOT=/path/to/recovery/state
CROSS_MARKET_SNAPSHOT_ROOT=/path/to/cross-market/snapshots
```

The audience IDs above are examples. With no target configured, offline rendering and CI tests remain available, and no messages are sent.

`DATA_PLATFORM_ROOT` is the default root for persistent runtime data. A-share reports default to
`$DATA_PLATFORM_ROOT/reports/market-intel/a_share_daily`; delivery receipts and scheduled recovery state default under
`$DATA_PLATFORM_ROOT/state/market-intel/`. `A_SHARE_OUTPUT_DIR`, `A_SHARE_DELIVERY_STATE_DIR`,
`SCHEDULED_RECOVERY_STATE_ROOT`, and `CROSS_MARKET_SNAPSHOT_ROOT` let a deployment override those locations.
Persistent entry points fail with a configuration error when neither the data root nor a required path override is set.

Production credentials and real delivery targets must be injected by the deployment environment. Do not commit tokens, private paths, raw data, receipts, or runtime state.

## Credentials

For local development, use the Git-ignored `api_keys.json` at the repository root. To create it, copy
`config/api_keys.json.example` to `api_keys.json` and fill in local credentials. The loader also supports
`API_KEYS_PATH`, the user configuration path `~/.config/market-intel/api_keys.json`, and selected provider
environment variables. CI and deployments should use their platform's secret management. Do not distribute
credentials in an `.env` template or commit real credentials or provider data snapshots.

The API-key example reserves the top-level `gold_api` field for
[gold-api.com](https://gold-api.com/) (not GoldAPI.io). Replace `YOUR_GOLD_API_KEY` only in your private JSON credential file. This placeholder does not enable a data adapter or change the daily report's pricing convention.

## Korea market fallback data

Korea daily proxy quotes do not require an API key. The runtime tries FinanceDataReader, then pykrx, then
yfinance. It records the selected `source` and sets `degraded=true`; proxy quotes are not official KRX or
NXT intraday data.

## AI market news

AI market news supports Zhipu GLM, Alibaba Bailian, and Google Gemini. The `ai_news` section of `api_keys.json`
can supply defaults; provider-specific environment variables override matching settings. For example,
`AI_NEWS_PROVIDER=aliyun` with `ALIYUN_MODEL=qwen3.7-flash` selects Alibaba Bailian's `qwen3.7-flash`, even
if the JSON still contains a general `model` value.

Each fetch emits one `ai_news_runtime` structured log record with the resolved `provider`, `model`, `base_url`,
and `fallback_order`. It contains no API key and can be used to verify the effective provider configuration.

## Cross-repository roots

Use explicit paths when a workflow invokes an owner CLI:

```bash
DATA_PLATFORM_ROOT=/path/to/data/market-data-platform
MDP_DIR=/path/to/quant-market-data-platform
QUANT_RESEARCH_ROOT=/path/to/quant-research
MARKET_INTEL_ROOT=/path/to/quant-intel-platform
```

The repository path is only a process entry point, not a Python import boundary. Validate the resulting artifact and receipt after the owner CLI completes. Production-specific configuration is maintained in `quant-intel-deploy`.
