# Asia news: source-dated, reviewed report evidence

Status: design for user review, not implemented or enabled.

## Intent and scope

Add understandable, attributed Asia news to the evening report without changing the meaning of the A-share market statistics. Reuse existing `daily_messenger` market-news adapters and market specifications. First implement mainland China and Hong Kong; Japan and Korea follow after equivalent source/time/calendar acceptance checks. No new scheduler, production cutover, model provider change or test message is part of the initial development.

## Data boundaries

Keep raw fetched documents, search results and candidate items outside the repository. A candidate is not an approved report claim. The public site consumes only reviewed public artifacts, never provider responses or private runtime paths. Existing legacy consumers remain unchanged until an explicit versioned adapter is ready.

For each candidate retain a stable evidence ID, market, canonical document URL, source publisher, original publication timestamp with timezone, retrieval timestamp in UTC, event date when explicitly stated, original language, title, short factual excerpt or paraphrase, content hash and revision relationship when known. The original document and retained response are the evidence authority. Date-only sources carry `time_precision: date`; do not manufacture a time or substitute retrieval date for publication date. Missing source dates remain missing and block same-day claims.

Use a new versioned Asia research envelope rather than silently tightening the legacy `normalize_news_items` contract for all existing callers. Preserve machine identifiers and timestamps independently of locale. Keep the reviewed statement, source event time and report publication cutoff separately represented.

## Collection and relevance

The existing market adapters collect candidates. A source host allowlist prioritizes exchange/company disclosures, central banks and statistics publishers but does not itself approve a statement. Enforce bounded timeouts, document size limits, finite retries and sanitized failure receipts. Respect source access constraints; do not bypass login or anti-bot controls.

China sources initially cover SSE/SZSE disclosures and original company announcements, plus original official policy or statistics releases. Hong Kong sources initially cover HKEXnews disclosures and original company announcements. Macro/geopolitical material must identify its relevance to the named market. No quota filling or forced explanation of price moves.

Classify source publication times against the evening cutoff, with explicit market timezone and authoritative local exchange calendar. Publication on a holiday remains a dated news item and is not labelled as a trading-session close explanation. An unavailable local calendar produces an explicit uncertainty status, not a weekday approximation. Cross-market holiday handling must not reuse the SSE calendar for Hong Kong.

## Independent review

Reviewers verify each statement against the retained original source, publication/event dates, numbers, units, entity identity and applicability at the report cutoff. Link approval to exact candidate content hash, reviewed claim hash, source URL/hash and review time. Later edits or source revisions invalidate the old approval. Models may propose candidates, translations and summaries; they cannot approve their own claims.

Verify the source's redistribution/display terms for the intended short paraphrase and link. Existing Tushare/Eastmoney authorization does not automatically authorize third-party news republication. Do not retain or publicly reproduce full copyrighted articles.

## Report and language presentation

Separate A-share and Hong Kong news subsections. Each short item includes source date, publisher and a direct document link. Facts, forecasts and planned releases are distinguished through plain language. State whether older information remains relevant when reused. Avoid mechanical mixed-language fragments, excessive disclaimers and unsupported causal attribution.

Publish independently reviewed English translations bound to the same exact claims. Missing English translation remains explicit and preserves the source-language evidence; it must not silently appear as fully translated content. No machine translation may change fact magnitudes, currencies or source dates.

## Acceptance before enabling

- Offline fixtures cover missing/naive timestamps, date-only precision, midnight timezones, cutoff violations, market holidays, stale calendars, duplicate documents, revised disclosures, absent URLs, unknown sources and tampered review hashes.
- Controlled read-only probes demonstrate accessible source documents for both markets. Access success does not prove claims or rights.
- At least one independently verified original disclosure for each market is rendered in both locales with correct dates, magnitudes, links and review identity.
- Empty or failed collection leaves an explicit report gap without breaking factual market sections or delivery idempotency.
- Complete platform/web gates pass before merging. Deployment pins and a no-send production canary require a separate production decision. Existing 07:00/19:00 personal delivery is unchanged.

## Implementation handoff

After this written design is approved, create the detailed implementation plan. Implement the envelope and offline validation first, collection adapters second, independent review integration third, and report presentation last. Do not treat this document as evidence that Asia news is already live.
