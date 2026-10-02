# U.S. daily report completeness

Bitcoin spot prices are required for the daily cross-asset review. The CME
continuous Bitcoin futures series (`BTC=F`) is optional and cannot replace spot
prices. An incomplete futures bar must not be presented as a verified daily close.

The pipeline records absent required spot data as `missing_sources: btc_spot`.
The public renderer checks each required close/return pair independently. Missing
optional futures are displayed under **Optional data unavailable**, not among
required data gaps. The original source-status diagnostics remain available.

Legacy public reports with a generic cross-asset gap are interpreted using their
verified facts. Missing spot remains a required gap even without an explicit
missing-source flag. A generic warning is suppressed only when the source status
explicitly records `reason: optional_futures_unavailable`; unknown diagnostics
retain their warning. This changes the
presentation boundary, not the market values, observation dates, or source rights.

Research drafts remain unpublished until an independent, hash-bound source audit
approves individual claims. Model completion is not source approval. Preserve
unverified claims as deferred; never fill missing sections merely to meet a quota.

Deploying runtime code, connecting reviewed research to scheduled production,
and repairing production paths require separate production authorization. A code
merge is not proof of production activation or a new message delivery.

The checked-in legacy browser bundle must match the TypeScript implementation.
Regenerate it from `web/` after changes:

```sh
npx esbuild src/lib/market-daily-utils.ts --bundle --format=iife \
  --global-name=marketDailyUtils --outfile=src/lib/market-daily-utils.js
```
