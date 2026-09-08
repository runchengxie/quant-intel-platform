# Operations Contract

This public document describes observable failure semantics and recovery interfaces. Host-specific runbooks, escalation targets, credentials, and production topology belong in `market-intel-deploy`.

## Failure semantics

- Missing optional data produces a marked degraded result where the pipeline supports fallback.
- Missing or stale required owner artifacts fails closed.
- Delivery without a configured destination is a no-send result, not an implicit broadcast.
- Receipts link the output artifact, audience role, idempotency scope, and outcome.
- Recovery commands must be bounded, auditable, and safe to re-run.

## Deployment boundary

Production operators configure explicit data roots, owner CLI paths, schedule definitions, and transport credentials outside this repository. The public code must remain runnable with synthetic fixtures and no secrets.
