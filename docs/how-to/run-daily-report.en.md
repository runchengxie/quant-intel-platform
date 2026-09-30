# Run the daily market report

[中文页面](run-daily-report.md)

## What the workflow does

The daily workflow fetches data, calculates topic scores, and renders reports in sequence. Outputs go to `out/` by default. It does not send messages automatically.

## Offline check

To confirm that the command is available without using live credentials:

```bash
API_KEYS='{}' uv run dm run --force-score
```

When an optional source is unavailable, the system records a fallback status. Completeness depends on local configuration and provider permissions.

## Run individual stages

```bash
# Fetch data only
API_KEYS='{}' uv run dm fetch

# Calculate topic scores only
API_KEYS='{}' uv run dm score --force

# Render the report only
uv run dm digest
```

Running stages separately helps isolate a failure.

## Inspect outputs

Common outputs include `out/etl_status.json` for retrieval status, `out/scores.json` for topic scores, `out/actions.json` for suggested actions, `out/index.html` for the daily page, and `out/digest_card.json` for message-card data. See [Artifact contracts](../contracts.md) for the complete field definitions.

## Use live data safely

Keep credentials in environment variables or a local Git-ignored file. Never commit real values or copy production outputs into this public repository. Production schedules and message destinations are managed by `quant-intel-deploy`.

## Cross-asset supplements for the US report

The US report prefers Yahoo continuous-futures daily data. If any of Brent, gold, or silver is missing, it may try FMP daily data for `BZUSD`, `GCUSD`, and `SIUSD` only when the private configuration addressed by `API_KEYS_PATH` contains `financial_modeling_prep`. FMP must return positive closes for the report date and the preceding valid session, and the report date must be past the instrument's completion time. The two-day return is calculated within one source. BTC continues to use Yahoo CME continuous futures; SoSoValue ETF flows are not a substitute for BTC price.

A separate `BTC/USD` spot series is also available. It prefers FMP `BTCUSD` end-of-day data for the report date and preceding date. On failure it tries authorized CoinGecko Pro `bitcoin/USD` hourly history, then Kraken `XBT/USD` hourly candles. The latter two use the completed 16:00 Eastern cutoff and compare with the same cutoff on the preceding day. All three write `cross_asset.bitcoin_spot.*` and record the actual source and observation convention; none overwrites the CME-futures fields under `cross_asset.bitcoin.*`. The CoinGecko key is stored outside the repository in the `coingecko` field of private `api_keys.json`.

Reject a source if the cutoff is missing or duplicated, its value is invalid, or the current time has not reached the cutoff. If all sources fail, keep the field missing instead of substituting a stale value. If network access blocks CoinGecko Pro, Kraken may be tried automatically, but Kraken observations must never be labelled as CoinGecko.

The output records source, code, and original observation date. FMP provides its continuous-futures daily series; the report does not claim these values equal official exchange settlement prices. FMP documentation links identify the API source, but access to individual raw records requires provider authorization. Public-display permission is based on the user's confirmation on 2026-09-26; the remote environment did not contain an authorization document. Operators must retain the authorization record and verify its exact scope.
