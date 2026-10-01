# Gold API reference integration status

## Verified on 2026-10-01

The private `gold_api` credential successfully authenticated XAU and XAG OHLC
queries. A deliberately invalid key returned HTTP 401. Live requests and the
private credential file are not part of the repository or CI.

The provider's [API documentation](https://gold-api.com/llms.txt) defines OHLC
over a requested segment. `startTimestamp` and `endTimestamp` echo the requested
boundaries; they are not the timestamp of the last price observation. A segment
ending in the future can return HTTP 200 while still containing partial data.
An entirely future segment returned HTTP 404 in the bounded diagnostic probe.
The provider's [homepage](https://gold-api.com/) labels its displayed gold price
as USD per ounce. It does not identify the underlying feed, establish the exact
XAG unit, or supply actual observation timestamps for historical segment closes.

The private reader `daily_messenger.daily_report.gold_reference` therefore:

- rejects future, unordered, timezone-naive and subsecond boundaries;
- validates exact returned bounds, finite positive numbers and OHLC ordering;
- uses only XAU/XAG and disables redirects to avoid forwarding the API key;
- exposes only safe error classifications, never raw HTTP bodies;
- leaves `actual_quote_time` unknown rather than inventing it from request bounds.

## Not enabled in production

This reader does not produce public facts, change completeness scoring, invoke
model research, or send Feishu messages. It must not be added to the five-minute
retry timer without persistent caching and quota controls: the provider documents
a shared free historical/OHLC limit of ten requests per hour.

Before public integration, obtain a verifiable quotation-unit and underlying
instrument/data-source definition, and establish a policy for segment freshness
when the last observation timestamp is absent. Commercial API use is permitted
by the provider's [terms](https://gold-api.com/terms), but that does not establish
whether the reference is spot, futures, or an exchange settlement.

Keep any verified reference series separate from COMEX dated-contract facts.
Never use it to silently clear the existing gold/silver futures completeness gaps.

## Private latest-price sampling

```bash
dm metal-sample --out /path/to/private/data/metal-reference-samples
```

This reads the free `/price/XAU` and `/price/XAG` endpoints, which do not require
the historical API key. Each successful invocation saves a new private JSON pair
with mode `0600`, the provider's actual `updatedAt` and a separate retrieval time.
Old samples are retained. Invalid identities, non-USD quotes, invalid prices,
timezone-naive or future timestamps, and partial pairs are rejected. An old
quote remains explicitly old; successful retrieval does not certify freshness.
Instrument and quotation unit remain unverified. No production sampler timer
or public integration is enabled by this command.

## Bounded original-source research

```bash
dm research --date YYYY-MM-DD --section market --out /path/to/private/data/research
```

Supported sections are `market`, `drivers`, `macro`, `company_news`, `gainers`
and `losers`. Single-section mode has a hard 180-second default subprocess timeout and
rejects payloads outside that section or with more than two candidates. The
prompt asks for at most two searches and two original-page opens, but this is
guidance, not a tool-enforced request counter. Candidates still require review;
empty output does not establish coverage. Omitting `--section` preserves the
existing broad research mode and its 480-second default timeout. Existing
production jobs are not automatically switched to single-section mode.

Use `--timeout-seconds 300` for a wider bounded research window, or up to `600`
for diagnostics. Explicit budgets must be integer seconds from 30 through 600;
the option overrides either single-section or full mode. Each invocation's
actual budget is recorded in both the draft and receipt. More time does
not waive source verification or make empty output complete. The 2026-10-01
private company-news probe completed in approximately 92 seconds with two
structurally valid candidates, illustrating why 75 seconds can be insufficient;
one probe does not establish production reliability.

This budget is per invocation, not a scheduler-wide allowance. Any future
multi-topic production caller must coordinate its total deadline, retries,
overlap locks and service timeout separately. No timer changes are made here.

Web research opens original news pages to verify publication time, observation
date and supporting evidence. This is unrelated to the public report site's
loading speed. Market prices continue to use data APIs, not news-page scraping.
