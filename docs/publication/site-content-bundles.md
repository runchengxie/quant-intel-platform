# Public site content bundles

[Chinese version](site-content-bundles.zh-CN.md)

The Platform provider exports the indexed public snapshot into a deterministic ZIP.
The verifier checks exact bytes, installed producer identity and public eligibility,
then creates an external input root containing artifacts/public/data and
artifacts/public/reports for market-export-site-snapshot. The provider does not
upload, dispatch a workflow, deploy a site or send messages. Production activation
and the Pages/Deploy consumers are separate changes.

## Installed commands

Install market-intel from the reviewed immutable Platform Git revision in an
isolated environment. Editable installs, plain directory installs, missing VCS
metadata and a caller-supplied revision that differs from the installed revision
are rejected. Run outside source checkouts with isolated Python (-I); console
entrypoints are also available.

Use configured external DATA_ROOT for every input, archive, receipt and output.
These shell variables describe synthetic example paths, not production state:

~~~bash
candidate="$DATA_ROOT/quant-intel-platform/example-content"
producer_revision="<reviewed-40-character-Platform-Git-revision>"
created_at="2026-11-01T00:00:00Z"
market-pack-site-content \
  --root "$candidate/input" --output "$candidate/content.zip" \
  --created-at "$created_at" --producer-revision "$producer_revision" \
  --receipt "$candidate/pack-receipt.json"
archive_sha256=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["archive_sha256"])' \
  "$candidate/pack-receipt.json")
market-verify-site-content \
  --bundle "$candidate/content.zip" --sha256 "$archive_sha256" \
  --output "$candidate/verified" --expected-producer-revision "$producer_revision" \
  --receipt "$candidate/verify-receipt.json"
market-export-site-snapshot --root "$candidate/verified" \
  --output "$candidate/reexported"
~~~

All destinations must be new, external and nonoverlapping. Existing destinations,
including empty directories, are rejected. Reuse the original archive and receipt
for retries; select a new destination when independently verifying them. Callers
must exclusively own output destinations while the command runs. Input errors do
not promote an output or receipt. Receipt write/promotion errors roll back the
paired promotion; no prior output is replaced.

## Identity and public eligibility

The manifest has schema_version market_intel.site_content_bundle.v1,
publication public, bundle_id, created_at_utc, producer and sorted files.
Each file records path, sha256 and bytes. Producer records owner
quant-intel-platform, distribution market-intel, source_revision and source_sha256.

The logical bundle_id hashes canonical UTF-8 JSON (sorted keys, compact separators,
finite numbers, no extra whitespace) of the manifest without bundle_id. The
archive_sha256 hashes the exact ZIP bytes separately. Neither is a Git revision.
The supplied UTC time is fixed once for a candidate, including its generated health
sidecar. Ordinary exporter health timestamps retain their existing behavior; a
later re-export therefore has its own output hashes.

The installed distribution must have real Git direct_url metadata for the expected
immutable commit. The provider verifies installed package files against RECORD and
hashes their sorted relative paths, byte lengths and measured SHA-256 values.
This source_sha256 covers the installed producer package closure, excluding
distribution metadata, entrypoint launchers and interpreter bytecode. It does not
hash dependencies or claim that original private raw report bytes are available.
A modified installed package fails verification. Version 0.1.0 alone does not
identify transport capability.

Before packaging, indexed Asia reports, charts/news, U.S. daily projections,
commentary and weekly recaps pass the owner's public contracts. Unknown nested
fields and missing required public markers fail; integrity hashes alone never
make data public. Historical source files outside the indexed publication windows
are excluded by the existing exporter. Extra files inside the exported payload or
transport are rejected. Raw source hashes and the exact historical continuous
commodity allowlist keep their existing meaning. No new numerical normalization
or report-generation logic is introduced.

## ZIP and receipt contract

ZIP contains manifest.json followed by sorted payload/data/... and
payload/reports/... regular files. Entries use ZIP_STORED, timestamp
1980-01-01 00:00:00, Unix regular-file mode 0644, no comments or extra fields.
Stored entries avoid compressor-version variation and decompression bombs. The
verifier recreates the canonical archive and requires identical bytes, rejecting
alternate local headers, prefixes and trailing material.

Limits: archive 64 MiB, expanded payload 256 MiB, each file 16 MiB, 4096 payload
files, manifest 2 MiB. With stored compression the archive cap also limits usable
payload size. Duplicate JSON keys or ZIP names, non-finite numbers, absolute/dot/
backslash/drive paths, case collisions, Windows device names, symlinks, hard-linked
input files, device members, unknown keys, digest/size changes and overlapping
inputs/outputs fail closed. No arbitrary ZIP extraction API is used.

The frozen ContentBundleReceipt has schema_version
market_intel.site_content_receipt.v1, bundle_id, archive_sha256,
producer_revision, created_at_utc and ordered file records (path, sha256, bytes).
JSON receipts live outside the archive and do not grant publication by themselves.
Preserve the original archive, manifest and receipts for downstream publication
audits. A successful provider command is not evidence of a deployed public site.

See [the public JSON Schema](https://github.com/runchengxie/quant-intel-platform/blob/main/schemas/public/site_content_bundle.v1.schema.json)
and [Platform publication boundaries](../platform-publication.en.md).

When updating a verified input root, the exporter always rebuilds data/health.json and data/us_daily_status.json. Their stale source contents are excluded. It also filters daily_summaries.summaries and insights.insights through the existing owner source-binding functions, and recomputes insights.outcomes. Surviving records retain strict public fields and evidence checks; the exported snapshot and verified archive require full bindings. The health check time must equal the manifest candidate time.

Markdown and image admission remains the owner's responsibility. The transport preserves indexed owner-admitted bytes and enforces declared Markdown/image hashes where the family contract has them (weekly recap and Asia news/report binding). Legacy report indexes without a download digest retain their existing admission contract. A transport digest does not establish that arbitrary prose is free of confidential information.
