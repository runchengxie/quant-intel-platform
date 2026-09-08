# Configuration

Configuration is divided into public-safe defaults and deployment-provided values.

## Public-safe environment variables

```bash
MARKET_INTEL_CLIENT_CHAT_ID=example_client_target
MARKET_INTEL_INTERNAL_CHAT_ID=example_internal_target
MARKET_INTEL_PUBLIC_CHAT_ID=example_public_target
DATA_PLATFORM_ROOT=/path/to/local/data
```

The audience values above are examples only. Empty destinations are valid for offline rendering and CI; no message is sent when no target is configured.

## Credentials

Credentials must be supplied through environment variables, a local ignored file, or the credential mechanism required by the relevant provider. Do not commit real values, local `.env` files, or provider response snapshots.

## Cross-repository configuration

Research and data owners are configured through explicit paths and public CLI contracts. The public framework does not import adjacent repository source or infer paths from a developer's home directory.

Production-specific configuration is maintained in `market-intel-deploy`.
