# Public weekly recap handoff

Publish only an approved public report and image. Owner artifacts remain private;
Platform copies allowlisted observations and source digests, never raw owner JSON.
Customer names, recipients, runtime paths and credentials must be removed before
approving Markdown/image for public export. Explicit public approval is required.

```bash
market-export-weekly-recap --report /external/public-weekly.md \
  --image /external/public-weekly.png --value-artifact /external/value.json \
  --size-artifact /external/size.json --date 2026-10-23 \
  --output /external/weekly-bundle --publication public
market-import-weekly-recap --bundle /external/weekly-bundle --root /checkout/pages --dry-run
market-import-weekly-recap --bundle /external/weekly-bundle --root /checkout/pages
market-export-site-snapshot --root /checkout/pages --output /external/site-snapshot
```

The bundle has exactly `weekly_recap.json`, `<date>-weekly.md` and
`<date>-weekly.png`. The import publishes `artifacts/public/data/weekly_recap.json`,
`data/weekly_recaps.json` and the bound Markdown/PNG under `reports/`. It validates
all retained records, stages updates and replaces the public directory with rollback
on replacement failure. Callers must serialize all public-directory writers using
the publisher lock; atomic directory replacement does not coordinate concurrent writers.
A dry run validates without writing. Failed validation preserves the prior publication.
Snapshot export includes only validated indexed records. Daily pruning preserves weekly
files. Weekly retention removes only the oldest weekly indexed assets beyond five dates.

Identity uses calendar Friday. Both admitted owner artifacts and final series observations
must cover that Friday; holiday weeks with no Friday observation skip publication in v1.
Old imports cannot roll back a newer public week. Historical first publication is allowed;
operational freshness and delivery windows are enforced by Deploy, not this archival CLI.
Generation timestamps carry an explicit time zone and cannot precede the cutoff date.

The schema is `market_intel_pages.weekly_recap.v1`; see
[the execution contract](https://github.com/runchengxie/quant-intel-platform/blob/main/docs/superpowers/specs/2026-10-24-weekly-pages.md) and
[JSON Schema](https://github.com/runchengxie/quant-intel-platform/blob/main/schemas/public/weekly_recap.schema.json). The public Python API is
`market_intel_publication.weekly_recap_contract.validate_weekly_recap(payload)` and
`content_hash(payload)`. Python canonical JSON uses sorted keys, compact separators,
UTF-8 without ASCII escaping, and rejects non-finite numbers. The entire payload except
`content_hash` participates in the digest. Markdown equality binds the full text;
PNG SHA-256 and dimensions bind the image; owner SHA-256 values bind original inputs.
Consumers independently validate the digest and sanitize Markdown when rendering.

Value owner fields map `ret_12w * 100` to `return_12w_percent` and `cum` to
`wealth_index`; size fields map `small`/`large` to crowding without calculations.
Value regime is `MOMENTUM` or `NEUTRAL`, streak is a positive integer, and size signal
is `small_cap`, `large_cap` or `insufficient`. Value history is limited to 104 observations,
size history to 252. Dates are ordered, unique, bounded by the cutoff and end on it.
PNG inputs are at most 20 MB, 20,000 pixels per dimension and 40 million total pixels.
JSON inputs are at most 5 MB and Markdown at most 1 MB. Symlink inputs and destinations,
unknown public fields, unsafe paths, invalid enums, stale owner data and hash mismatches
fail closed. This flow performs no messaging or production deployment.
