# Public US daily report status

The `market-export-site-snapshot` CLI adds `data/us_daily_status.json` to every
snapshot. Its schema is `market_intel_pages.us_daily_status.v1`, defined in
`schemas/public/us_daily_status.schema.json`. The `reports` list contains the same
rolling public US report window as `market_daily_reports.json` (or its latest-only
fallback). An empty public US report window produces an empty list.

Each record binds `run_id`, `date` and the original report `content_hash` to a
`report_status` object and sorted `missing_market_facts`. Consumers must match all
three identity fields before displaying the status. The public report bytes and
signed source identity remain unchanged; the sidecar is an additive projection.

- `market`: `complete` or `incomplete`. Coverage requires the target-date finite
  numeric facts with quality `ok` or `reviewed`: four index changes, six core
  equities' closes and changes, four Treasury tenors' levels and basis-point
  changes, and Brent, gold, silver and Bitcoin spot closes and changes (32 facts).
  Optional Bitcoin futures and monthly macro observations are excluded.
- `research`: `reviewed` requires a reviewed research source status and an accepted
  public claim with evidence IDs present in the report and HTTPS sources.
  `not_included` means no public claims or explicitly `not_connected` research;
  it does not imply a pending review. Other combinations are `unknown` because
  the public report does not contain a review workflow receipt.
- `publication`: `published`. Records describe already public reports; missing
  expected reports are a deployment freshness concern.

The sidecar contains only the documented fields. It exposes neither private
research receipts nor internal paths. Overall legacy `quality_summary.status`
remains available and is not rewritten by status export.
