# Asian index operational recovery

The optional deployment wrapper runs the existing cross-market fetch once, then
requests only missing or stale HSI, N225 and KS11 closes from the data owner.
The report consumes the finalized `overseas-index-operational-v1` receipt:

```bash
python -m a_share_daily.fallback_fetch --date 20261021 --json --recover-receipt /data/run/receipt.json --receipt-root /data/run --input-snapshot /data/initial.json --observed-at 2026-10-22T01:00:00+00:00
```

This mode performs no provider requests. It validates hashes, paths, sizes,
source times and exact target/preceding market sessions. It recovers only invalid
or missing quotes and computes returns using the same source. Valid first-choice
quotes and unrelated errors remain unchanged. Recovered quotes retain source,
route hostname, receipt path/hash, CSV hash, actual receive time and initial
attempt diagnostics. Omit `--observed-at` to use the current aware UTC time;
explicit cutoffs cannot be in the future. Never replay a later receipt as if it
were available to an earlier report. Paths are internal diagnostics and should
not be exposed as public report text.

A typed Yahoo rate-limit exception suppresses subsequent Yahoo calls in the run.
Ordinary insufficient bars do not imply HTTP 429. Deployment persists cooldowns:
15 minutes initially, increasing to 60 minutes on consecutive failures. The
pure policy accepts Retry-After when available; yfinance's typed exception does
not currently expose that header. Other Yahoo consumers are outside this scope.
