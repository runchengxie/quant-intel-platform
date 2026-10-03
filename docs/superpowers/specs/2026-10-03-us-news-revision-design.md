# Reviewed U.S. news revisions and date-only sources

Status: proposed design, awaiting written-spec review. No implementation or
production activation is included in this document.

## Intended outcome

Add reliable news background to an existing U.S. daily report without changing
its market facts. Accept sources that provide only a publication date without
inventing a publication time. Company-owned announcements and original filings
are preferred. Evidence review and permitted use remain independent gates.

The user approved this direction on October 3, 2026. This spec defines the
interfaces required before implementation. It does not authorize automatic
source approval, a production switch, or message delivery.

## Current behavior

`daily_messenger.daily_report.reviewed_research` requires a timezone-aware
`published_at`. `MarketEvent.source_time` is also mandatory. The public importer
and deployment validator assume precise event timestamps. The public projection
currently drops publication-time details from events.

`dm daily-report` collects market facts again when adding reviewed research.
The October 2 revision demonstrated that a news addition can unintentionally
change commodity quotations or the Bitcoin observation basis. A separate
offline revision path must prevent this.

## Selected approach

Extend the existing review contract and CLI. Keep the normal market-report
generation path unchanged. Do not create a second news scraper, scheduler,
automatic reviewer, or data-fetching pipeline.

Two alternatives are excluded: assigning midnight to date-only sources would
fabricate precision, and rerunning the full report then restoring quotations
would still perform unnecessary network calls and make preservation harder
to verify.

## Publication-time evidence

Introduce explicit publication precision for reviewed events in report schema
`1.1`. Continue accepting existing `1.0` precise-time artifacts unchanged.
Omit new default fields when serializing legacy artifacts so their hashes and
public projections do not change solely through a parser round trip.

- `timestamp`: retain the verified timezone-aware `source_time`. Record whether
  it is original publication time or filing acceptance time. Do not silently
  substitute the latter for the former.
- `date`: retain a strict `source_date` and a verified IANA `source_timezone`,
  or explicitly mark the timezone unknown. `source_time` is null. Record
  `publication_precision: date` and `usage: background`.

For a verified timezone, derive the possible publication interval from that
local calendar day, respecting daylight-saving changes. With unknown timezone,
use conservative global bounds from UTC+14 through UTC-12. These bounds are
validation aids, never displayed as an actual publication time.

Accept date-only material only when the complete possible interval is before
the declared news cutoff and its source date is no later than the report date.
An interval crossing the cutoff remains deferred. Missing timezone does not
justify assuming the publisher's headquarters timezone. Reject malformed dates,
conflicting precision fields, naive exact timestamps, and future evidence.

Date-only material is allowed in macro and company-background sections. It
cannot supply index returns, mover quotations, or close-move causal claims.
Intraday articles remain separate evidence and are not promoted to close data.

## Offline news-only CLI

Proposed interface, not an existing command:

```text
dm daily-report --date YYYY-MM-DD --revise-news INPUT_REPORT \
  --input-manifest PUBLIC_MANIFEST --reviewed-draft PRIVATE_DRAFT \
  --reviewed-decisions PRIVATE_REVIEW --out PRIVATE_STAGING
```

The revision path must validate the input schema, content hash, public manifest,
report date, complete review decisions, and exact draft SHA before writing.
It must not load provider credentials, call market-data suppliers, invoke a
model, import into the website, promote production files, or send messages.
Its output directory must not overlap the input artifact directory.

Retain the complete facts array exactly, including order, values, quality,
sources, observation dates, and retrieval timestamps. Retain all non-research
source status, section fact references, prior events, and accepted claims.
Reject review decisions that attempt to add quotations or mover ticker inputs
in this mode. Their presence must not be silently ignored.

Append only independently approved summaries and their evidence. Namespace new
evidence IDs using the full draft hash and candidate index to avoid collisions
between drafts. Do not rename existing evidence IDs. Identical accepted items
are no-ops. Conflicting content under an existing identity fails closed.

Keep the original `as_of` as the market-fact cutoff. `generated_at` records the
actual revision assembly time. Add explicit news-revision metadata: original
artifact SHA, previous content hash, news cutoff, revision time, and
`revision: news_only`. The news cutoff is independent of the original market
cutoff and cannot exceed the revision time. Do not use the existing
`next_morning_rechecked` label to imply retained quotations were refetched.

Recompute the content hash through the owner's shared serialization contract.
Write staged outputs only after validation succeeds. A repeated input and
review with no new claims produces no new revision or artificial timestamp
bump. Incomplete news must never prevent the ordinary market report from
being generated.

## Review and display boundaries

An approval records source location, independently checked facts, publication
precision, and the applicable display basis with its scope and verification
date. These review records remain private. A public-accessible URL alone is
not treated as permission to reproduce an article or illustration.

Prefer short, independently written factual summaries of original company
announcements and filings. Do not carry publisher wording, article photographs,
logos, or unsupported media causality into the report. Until the applicable
display basis is checked, an item stays deferred even when its numbers match.

Public events preserve publication precision and source dates. Chinese and
English catalogs provide date-only, unknown-timezone, retained-market-cutoff,
and news-revised-at labels. Web, SVG, Markdown, and text downloads distinguish
original market observations from the later news revision. Unknown English
prose retains the existing explicit source-language boundary and cannot be
partially translated into mixed-language sentences.

Show unavailable news sections explicitly. One accepted macro paragraph does
not imply that company news or market drivers are complete. No report date,
quotation, or delivery identity changes with locale.

## Validation and release order

The public owner implements the contract, models, offline CLI, importer,
renderers, regression tests, and documentation. The deployment repository then
updates its artifact validator and optional staging bridge through the public
CLI. Merge the provider before its consumer. Do not switch production to an
unmerged worktree or relax the old validator to accept unchecked fields.

The existing promotion and Pages publisher remain responsible for publication.
Keep the old artifact and manifest available for rollback. Personal delivery
deduplication remains keyed by kind, report date, and audience, not content hash.
This project does not remove sent receipts or trigger a resend.

Production synchronization, code release activation, and unattended scheduling
require a separate scoped authorization after local and required remote checks.

## Acceptance criteria

- Legacy timestamp reports round-trip without hash or projection drift.
- Date-only evidence never gains a fabricated time or close-causality label.
- DST days, unknown timezone, cutoff crossings, and future dates fail or defer
  according to the interval rule.
- A news revision preserves every original fact and non-research status exactly.
- Tests prohibit all network, credential, model, and send operations during
  offline revision.
- Tampered input manifests, mismatched draft hashes, missing decisions, ID
  collisions, attempted quote changes, and overlapping paths fail before writes.
- Repeating an already applied review is idempotent.
- Both validators reject inconsistent time metadata and unsafe lineage.
- Chinese and English web/SVG/downloads show publication precision and separate
  market and news times. Missing sections remain visible.
- Root daily-report tests and full owner gate pass. Website coverage remains at
  least 85%, browser checks pass, and deployment smoke tests pass before release.
- No current report, production configuration, timer, or Feishu receipt changes
  during development and no-send acceptance.

Company-source ingestion follows this implementation. Existing deferred
candidates are reassessed under the new time contract and source-use review,
not grandfathered into approval by this design.
