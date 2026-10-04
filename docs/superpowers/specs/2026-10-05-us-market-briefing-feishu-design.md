# U.S. Market Briefing Feishu Integration Design

## Status

Approved for implementation on 2026-10-05. Phase 1 adds the public bundle consumer and no-send preview in PR #195. Phase 1 does not resolve destinations, invoke Feishu, or enable a schedule. Live delivery remains a separate task after the audience and rollout scope are confirmed.

## Goal

Deliver a reviewed, five-paragraph Chinese U.S. market close briefing through the existing quant-intel-platform reporting and Feishu delivery paths. Keep the producer, consumer and private deployment responsibilities separate, and make the handoff inspectable and retry-safe.

## User intent and constraints

- The briefing is generated from a frozen evidence package by quant-market-briefing.
- A separate Chinese editing stage formats the report. It must not add or change facts.
- The result should be consumable as a versioned JSON artifact by quant-intel-platform.
- Feishu delivery should reuse existing platform delivery and receipt patterns.
- The final Feishu audience is not selected yet. The design must not hard-code a chat or recipient.
- Research/model evaluation settings remain documented as future work; routine implementation should not incur model API usage.
- No production schedule, credential or real message is part of this change.

## Existing interfaces and constraints

The producer emits a `research.platform-publication.v1` manifest targeting the compatibility consumer ID `market-intel`. Its bundle contains `briefing.json`, `review.json`, `evidence.json` and `analysis.json`. The manifest publishes briefing and review files with SHA-256 hashes. The review record binds the evidence, analysis and final briefing hashes, and records a decision for every claim in the final text.

`market.briefing.v1` contains exactly five paragraphs, `brief_text`, a headline, thesis, source links and validation results. Producer-side numeric and editorial validation does not set `source_audit_passed` to true. Source approval is a separate review artifact. A bundle is eligible for the formal delivery path only when the review record is valid, bound to the exact files, and every final claim is approved.

quant-intel-platform already provides a generic publication-manifest verifier, Feishu sending paths, delivery receipts, idempotency patterns and failure handling. It does not yet understand these U.S. briefing contracts. The platform must not import quant-market-briefing source code.

## Approaches considered

### A. Add a U.S. briefing consumer beside the existing global-market reporting flow — recommended

Add a focused adapter in the market-intelligence reporting area. It validates the publication bundle, constructs the existing report/delivery representation and delegates to the established Feishu sender and receipt flow. This keeps the new contract logic close to global-market reporting without changing A-share strategy delivery.

### B. Route the briefing through the A-share daily-report package

This package has mature publication and delivery controls, but its report concepts and CLI are A-share-specific. Adding U.S. market content there would couple two products with different calendars and report schemas.

### C. Create a new top-level briefing application in quant-intel-platform

This provides a clean boundary but adds another app, configuration surface and operational path for a product that can reuse the existing market-intelligence reporting and delivery infrastructure.

## Design

### Bundle validation

The consumer accepts a bundle directory and validates it before rendering or sending:

1. Parse `research.platform-publication.v1` using the pinned shared contract package.
2. Require the `market-intel` consumer ID, an allowed `internal` or `public` audience, and exactly one supported `market.briefing.v1` artifact and one `market.source-review.v1` artifact.
3. Resolve only the fixed bundle filenames. Reject absolute paths, traversal, symlinks escaping the bundle, duplicate artifact IDs and unsupported schema versions.
4. Recompute manifest artifact hashes and compare them with the referenced bytes.
5. Validate the briefing and review structures against the consumer's supported v1 contract. Keep the producer as schema owner; add a contract fixture/equivalence check so producer schema changes cannot silently drift from consumer support.
6. Verify market/date/run identity, review timestamp, and exact SHA-256 binding from the review record to evidence, analysis and briefing.
7. Require review decisions to cover exactly the claim IDs present in all five paragraphs and require every decision to be `approved`. Reject drafts, missing approvals, deferred or rejected claims, and malformed or missing source links.
8. Recompute the five-paragraph text from paragraph records and require it to equal `brief_text`. Reject any inconsistency rather than editing it.

The adapter does not call a model, modify wording, infer missing sources, upgrade audience, or treat a producer validation flag as source approval.

### Rendering and delivery

Render the headline and five paragraphs as plain, readable Chinese text with source links in a compact footer or existing supported card representation. Reuse the existing platform's sender, audience configuration and receipt conventions. The exact rendering should be settled against one synthetic representative preview before merge.

Use a stable delivery identity containing product, market date, revision and target identity. A repeated attempt for the same identity must consult the existing receipt/idempotency behavior and must not create a second message. A new briefing revision may be delivered only through an explicit revision policy; it must not be mistaken for a retry.

Provide a no-send preview path that validates the same bundle, produces the exact rendered payload and an explicit `dry_run` receipt, and never calls the Feishu API. Missing audience configuration must fail before the send path. Destination values and credentials are deployment configuration kept outside the public repository.

### Deployment boundary

quant-intel-deploy owns immutable version pins, stable runtime paths, private destination mapping, credentials, schedule, retry window, recovery state and production delivery receipts. A scheduled run should select the most recent completed U.S. exchange session after a configurable data-availability delay. Holidays, early closes, late producer output, expired retry windows and duplicate invocations must be explicit states.

This design does not choose a real recipient or schedule time and does not enable a timer. The first deployment milestone is local/synthetic no-send validation. Any live rollout is a separate task.

### Research review policy

Formal delivery requires a separate source-review record with every final claim approved. Human review remains the v1 authorization mechanism. Automated model review may be evaluated later, but it cannot silently replace or self-certify this gate. An unreviewed draft is not eligible for the formal daily delivery path.

## Failure behavior

All bundle, schema, hash, date, audience and approval failures stop before rendering is accepted for delivery. Send failures produce a failure receipt with the same delivery identity and enough diagnostics for bounded recovery. A successful send receipt records the manifest identity/hash, briefing date and revision, destination identifier (in private runtime state), message/provider response identity and completion time. Secrets and full private destination mappings must not enter public logs or repository artifacts.

## Acceptance criteria

Phase 1, the approved scope for PR #195:

- A valid synthetic v1 internal bundle passes validation and previews exactly five paragraphs plus source references.
- A public bundle is accepted in public mode; an internal bundle fails closed unless the caller explicitly opts in.
- Tampered briefing/review/evidence/analysis bytes, path traversal, unsupported versions, date/run mismatches and hash mismatches fail closed.
- Missing, extra, duplicate, deferred or rejected claim decisions fail before preview.
- A changed `brief_text`, missing source URL, non-five-paragraph report, or draft status fails before preview.
- The preview JSON contains `dry_run: true` and the exact rendered text. Running it never reads destination configuration or makes a network or subprocess call.
- Tests use synthetic fixtures only. Public CI does not access live market data, model APIs, credentials or Feishu.
- Documentation describes the supported consumer version and keeps real audience/schedule settings in quant-intel-deploy.

Later live-delivery scope, requiring the destination and rollout scope to be confirmed:

- Repeating an identical product/date/revision/target attempt does not send a duplicate; changing revision has an explicit test and receipt identity.
- Missing destination configuration and sender failures produce actionable failure results without exposing secrets.
- Delivery uses the existing platform sender and writes a private receipt without changing or re-generating the approved text.

## Out of scope

- Selecting or configuring a real Feishu group, person or application.
- Sending real messages, enabling schedules or changing production state.
- Running Codex research or model-evaluation experiments as part of CI.
- Rewriting the generated Chinese report during rendering or delivery.
- Building another market-data ETL or importing producer business logic into quant-intel-platform.
- Public website publication of the report.

## Decisions for review

1. Approve the recommended location beside the global-market reporting flow, rather than the A-share package or a new top-level application.
2. Approve the v1 gate that requires an independently created source-review artifact approving every final claim before formal delivery.
3. Confirm that the audience remains a deployment-time setting and that this implementation stops at no-send validation until a separate live-delivery task defines the destination and rollout scope.
