[Chinese version](us-market-briefing.md)

# U.S. market briefing: evaluation and Feishu integration

This page tracks work across quant-market-briefing, quant-intel-platform, and the private quant-intel-deploy repository. It describes planned integration; it does not enable a production schedule or authorize delivery to a real audience.

## Current state

quant-market-briefing produces five Chinese paragraphs, machine-readable claims, source records, and a versioned market.briefing.v1 artifact. It also uses the existing research.platform-publication.v1 publication envelope. The most recent deep run used Astra Extra High for the first research round, Astra High for a second live-search challenge, and GPT-6.1 Sol Medium for editing. This is a provisional, quality-first profile. One sample showed useful corrections and counterevidence, but did not establish forecast skill or the best model settings. The three model calls took about 30 minutes.

Mechanical validation does not approve sources. The briefing's source_audit_passed remains false until a separate review record approves the claims. The producer does not know the Feishu audience, credentials, or production schedule.

quant-intel-platform already owns report rendering, Feishu delivery, delivery receipts, and related fail-closed tests. It does not yet have a consumer adapter for market.briefing.v1 and market.source-review.v1. The private deployment repository owns real destinations, credentials, stable production paths, and schedules.

## Proposed ownership and flow

1. quant-market-briefing produces a versioned report and publication bundle without importing consumer source code.
2. quant-intel-platform verifies the publication envelope, briefing and review schemas, file hashes, source-review binding, and disclosure audience before rendering the five paragraphs.
3. The consumer prepares the reviewed report for the existing Feishu delivery layer, records a delivery receipt, and uses a stable idempotency key for the report date.
4. quant-intel-deploy pins a released consumer and producer version, supplies private configuration, and schedules work against completed U.S. exchange sessions. Credentials, destinations, reports, and receipts remain outside the public repository.

The existing generic publication verifier alone is insufficient: the consumer must understand both market schemas and must stop if the review binding or audience check fails. The publishing path must not send drafts that have not passed the required source review.

## Follow-up work

### Model and research evaluation

- [ ] Record actual token usage or another available usage measure alongside the existing requested model, effort, and elapsed-time metadata.
- [ ] Build a replayable evaluation set with frozen evidence and identical prompts, so model and reasoning-effort changes can be compared without repeating live web research.
- [ ] Compare factual corrections, source support, useful counterevidence, direction clarity, runtime, and usage. Do not score a stronger or more bullish tone as a better forecast.
- [ ] Preserve data vintages and later evaluate the stated one-to-four-week and six-to-twelve-month views against realized outcomes. A single session is not enough to establish forecast skill.

### Feishu consumer and deployment

- [ ] Add a market.briefing.v1 / market.source-review.v1 consumer adapter and contract fixtures.
- [ ] Render the report into an existing Feishu post format without asking the model to rewrite or shorten it during delivery.
- [ ] Add idempotency and delivery-receipt coverage, including duplicate attempts, rejected reviews, and missing audience configuration.
- [ ] Add deployment entry points and scheduler definitions only in quant-intel-deploy, using explicit version pins and private configuration.
- [ ] Exercise a no-send path, session-calendar and holiday behavior, retries, and freshness recovery before considering a live recipient.
- [ ] Confirm the destination audience and first live-send scope before configuring a production target.

## Boundaries

Public CI may run contracts, synthetic examples, rendering tests, and mocked Feishu delivery. It must not read credentials, contact Feishu, fetch live market data, or schedule model calls. Real delivery is a private deployment concern and requires the appropriate source review, audience, idempotency receipt, and operational recovery path.
