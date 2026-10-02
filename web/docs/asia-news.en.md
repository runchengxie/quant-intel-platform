# Reviewed Asia news

The versioned candidate, review and public artifact contracts cover mainland China and Hong Kong. Japan and Korea remain subsequent extensions. These modules do not start collection jobs, call a model, approve claims, or send messages.

## Intake and review

`collect_asia_candidates` accepts the existing market-news adapter's structured items (`url`, `source`, `published_at`, `title`, `summary`) or the explicit new candidate fields. Date-only values remain date-only. The original document's bytes, retained externally by the caller, determine its source hash. `BoundedDocumentFetcher` rejects redirects, reads at most 2 MiB, uses a 30-second attempt budget and retries transport errors at most once. A custom injected callback must enforce equivalent I/O bounds itself.

Use `review_template` to prepare an unapproved receipt. Independent review must verify the actual retained source, dates, facts, intended display rights and market-specific calendar. Candidate validity, source access and host allowlisting are not approval. The receipt binds exact candidate, source, claim and translation content. Date-only material on the cutoff day, unavailable calendar coverage, after-cutoff material and withdrawn documents cannot become public claims. Revisions require a new receipt. Holiday information is explicitly background context.

English translations require a separate content-bound attestation. Numeric-token checks catch obvious magnitude changes but cannot establish correct units, currencies, entity identity or meaning; the independent reviewer must check those against the source. Missing English translation retains the source-language claim with an explicit label.

## Optional publication

`a_share_daily.public_report_refresh` accepts an optional `--reviewed-asia-news PATH` pointing to a private `market_intel.asia_news_review_bundle.v1` object with an `items` list. Every item contains the exact `candidate` and independent `review` objects. Without this flag, the existing report workflow is unchanged. The optional news cutoff is 19:00 Beijing time on the report date, and public generation must be at or after that cutoff.

The report publisher projects only approved public fields into `market_intel.asia_news_public.v1`, binds the artifact to the exact Markdown SHA256, and adds `asia_news_path` to the import manifest. `import_reports` validates the sidecar before publication, preserves news revisions externally, and removes stale news when its report is corrected without a new reviewed sidecar. The five-date public window still applies. The site performs local file reads only; it does not browse for news during build or rendering.

## Acceptance status

The hard request budget includes blocked header/body reads. The default fetcher
requires a main-thread Unix CLI and an unused process timer; other execution
contexts fail closed. It restores the original signal handler after every attempt.
Translation review must follow source retrieval and precede public generation.
Duplicate document versions are suppressed and explicit revisions supersede their
old evidence. Conflicting unlinked versions block publication.

Public readers reject unknown fields. Imports preflight all retained news and
stage the complete snapshot before replacement, restoring the old snapshot if
replacement fails. Reimporting identical inputs repairs missing or changed news
sidecars. The supported website build stages only indexed news and validates each
artifact against its staged Markdown before Astro reads it.

Offline synthetic fixtures are test evidence only. They are not real disclosures or live news approvals. No automatic production collection, production activation, accepted live news, scheduler change or Feishu test message is implied by merging this feature. Before enabling, verify accessible original documents for both markets, actual display terms, independent claim/translation review and a no-send canary against the selected release. Existing 07:00/19:00 personal delivery remains unchanged.
