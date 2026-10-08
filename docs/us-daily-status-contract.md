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

## Index close enrichment

New deterministic reports include `index.<key>.close` facts for `spx`, `dow`,
`nasdaq` and `russell2000`, using `metric: index_close`, `unit: points`, same-day
Yahoo completed daily bars and the corresponding history URL. Old return-only
reports remain valid. New close sets must contain all four positive finite
numeric values and their existing daily returns. Index closes are additive and
do not change the 32-field market completeness policy.

To create an isolated candidate from a signed original report while preserving
its facts, claims, research status and market cutoff:

```bash
market-enrich-index-closes --input /external/original/daily_report.json \
  --manifest /external/original/publication.json --output /external/new-candidate
```

The command rejects newly acquired close evidence whose truthful `source_time`
is later than the original report `as_of`, before creating output. A retrospective
fetch normally falls into this case: it is not a publish-ready enrichment. Never
backdate retrieval-derived timestamps to make a candidate pass. A previously
rendered supplemental preview must remain private and must not be promoted.
Ordinary future generation includes the four closes in its original report.

The command fetches all four same-day bars, checks their returns against the
retained report (0.0051 percentage-point rounding tolerance), and fails before
staging on conflict or unavailable sources. It writes a newly hashed report and
signed publication manifest, the unchanged parent, and a versioned private
`index_close_enrichment.json` lineage receipt. Keep the parent and receipt outside
public assets. This command stages a candidate; production promotion and public
publication use the deployment workflow. It rejects existing `news_only`
revisions, because changing market facts requires a separate market revision
contract. It also rejects reports already containing closes.

Run the CLI from an immutable merged Platform release or wheel. Preview generation
can use that wheel and an external candidate directory without switching the
production release. Existing reviewed-return-only pipelines may still omit index
closes; a source-verified enrichment is needed for those reports.
