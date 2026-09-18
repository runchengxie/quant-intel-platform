# Analysis and style bridge migration plan

## Goal

Move research calculations out of `market-intel` while keeping its reporting and operational
publication responsibilities small and explicit.

## Migration batches

1. **Value regime** — move `src/a_share_analysis/value_regime_weekly.py` calculation, episode
   detection, and forward-return evaluation into strategy-pipeline; publish a versioned weekly
   regime artifact with inputs and as-of dates. Market-intel consumes and renders it.
2. **Size/style** — move `src/a_share_analysis/size_style_weekly.py` crowding, relative-strength,
   and timing calculations into strategy-pipeline; publish a matching weekly artifact and keep
   only presentation-side loading in market-intel.
3. **Style-factor bridge** — make strategy-pipeline the owner of factor refresh and metadata.
   Market-intel keeps only the shell compatibility entrypoint and consumes the published artifact
   in reports.

## Boundary rules

- Research workspace owns computation, model inputs, feature definitions, and statistical outputs.
- Market-intel owns information push: chart/report composition, delivery, freshness checks, and
  consumer validation.
- Every migrated output gets a schema version, source/as-of dates, lineage, quality status, and
  atomic publication semantics before callers switch.
- Keep compatibility readers during one observation window; remove producer shims only after
  consumer and watchdog coverage is proven.

## Verification

For each batch, add producer contract tests first, then consumer compatibility tests, receipt/hash
checks, stale-artifact watchdog tests, and a dry-run of the affected morning/weekly report.
