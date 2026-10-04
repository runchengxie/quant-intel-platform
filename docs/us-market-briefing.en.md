[Chinese version](us-market-briefing.md)

# U.S. market briefing: evaluation and Feishu integration

This page documents the integration across quant-market-briefing, quant-intel-platform, and the private quant-intel-deploy repository. The public implementation validates publication bundles and creates an offline preview; it does not enable a production schedule or send messages to a real audience.

## Current state

quant-market-briefing produces five Chinese paragraphs, machine-readable claims, source records, and a versioned market.briefing.v1 artifact. It also uses the existing research.platform-publication.v1 publication envelope. The most recent deep run used Astra Extra High for the first research round, Astra High for a second live-search challenge, and GPT-6.1 Sol Medium for editing. This is a provisional, quality-first profile. One sample showed useful corrections and counterevidence, but did not establish forecast skill or the best model settings. The three model calls took about 30 minutes.

Mechanical validation does not approve sources. The briefing's source_audit_passed remains false. A separate source-review record must bind the evidence, analysis, and briefing hashes and approve every final claim before the consumer accepts the bundle. Neither the producer nor public preview command reads Feishu destinations, credentials, or production schedules.

quant-intel-platform now has a consumer validator for market.briefing.v1 and market.source-review.v1, plus a local preview command. The changes are in PR #195 and have not been released. The preview displays the original text, headline, and source links without contacting Feishu. The private deployment repository continues to own real destinations, credentials, stable production paths, and schedules.

```bash
uv run dm us-briefing-preview --manifest PATH --allow-internal
```

Internal bundles require the explicit `--allow-internal` flag. The command prints `market.briefing.preview.v1` JSON with `dry_run: true` and the complete rendered text. It contains no destination or send receipt.

## Proposed ownership and flow

1. quant-market-briefing produces a versioned report and publication bundle without importing consumer source code.
2. quant-intel-platform verifies the publication envelope, both v1 schemas, file hashes, source-review binding, and disclosure audience.
3. The public implementation currently creates an offline preview. A later Feishu integration can reuse the existing sender, receipt, and idempotency behavior, without rewriting the approved text during delivery.
4. quant-intel-deploy owns immutable producer and consumer pins, private configuration, and schedules based on completed U.S. exchange sessions. Credentials, destinations, reports, and receipts remain outside the public repository.

The existing generic publication verifier alone is insufficient: the consumer must understand both market schemas and must stop if the review binding or audience check fails. The publishing path must not send drafts that have not passed the required source review.

## Follow-up work

### Model and research evaluation

- [ ] Record actual token usage or another available usage measure alongside the existing requested model, effort, and elapsed-time metadata.
- [ ] Build a replayable evaluation set with frozen evidence and identical prompts, so model and reasoning-effort changes can be compared without repeating live web research.
- [ ] Compare factual corrections, source support, useful counterevidence, direction clarity, runtime, and usage. Do not score a stronger or more bullish tone as a better forecast.
- [ ] Preserve data vintages and later evaluate the stated one-to-four-week and six-to-twelve-month views against realized outcomes. A single session is not enough to establish forecast skill.

### Feishu consumer and deployment

- [x] Add a market.briefing.v1 / market.source-review.v1 consumer adapter and synthetic contract fixture.
- [x] Add a local no-send preview showing the original five paragraphs and source links.
- [ ] Connect Feishu post delivery, receipts, and idempotency. Send only the reviewed text without model rewrites.
- [ ] Add idempotency and delivery-receipt coverage, including duplicate attempts, rejected reviews, and missing audience configuration.
- [ ] Add deployment entry points and scheduler definitions only in quant-intel-deploy, using explicit version pins and private configuration.
- [ ] Exercise a no-send path, session-calendar and holiday behavior, retries, and freshness recovery before considering a live recipient.
- [ ] Confirm the destination audience and first live-send scope before configuring a production target.

## Boundaries

Public CI may run contract, synthetic fixture, and offline preview tests. It must not read credentials, contact Feishu, fetch live market data, or schedule model calls. Real delivery is later private deployment work and requires a confirmed audience, source review, disclosure isolation, idempotent receipts, and operational recovery.
