# Composite hotspot provider

The daily topic chart consumes `hotspot_composite_v1`. It is a report and
research artifact, not an implicit replacement for the production
DailyWatch20 candidate-pool contract.

## Evidence layers

- Core identity: `dc_concept` and `dc_concept_cons`.
- Market confirmation: `limit_list_ths` and `moneyflow_ths`.
- Optional breadth: `daily` stock returns, when the exact-date partition is
  available.

The artifact records `providers` and `source_status` for every layer. Missing
core identity data fails closed. Missing confirmation or breadth data produces
`degraded: true` and is visible to the report manifest; it must not be
silently represented as a fully confirmed hotspot.

The separate research candidate-pool mode is
`dc_concept_composite_strict_v1`. It remains research-only until a parallel
evaluation passes the data-coverage, return-path, risk, overlap, and
stability gates. Production DailyWatch20 remains bound to
`ths_hot_strict_v3` during that evaluation.
