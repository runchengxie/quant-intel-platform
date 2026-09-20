# Report Distribution Contract

The public framework exposes semantic audiences and transport interfaces. It does not contain real recipients, customer names, group identifiers, webhooks, or production routing policy.

## Public audience model

The framework recognizes these generic audience roles:

- `client`: an externally-facing report audience;
- `internal`: an engineering or research audience;
- `public`: an intentionally public output audience.

Production deployments map these roles to actual destinations in a private deployment configuration. A local or CI run with no destination configured must render and validate reports without sending messages.

## Delivery guarantees

Delivery adapters should preserve:

- audience isolation;
- deterministic idempotency keys;
- artifact and receipt linkage;
- fail-closed behavior when a required destination is absent;
- dry-run support for tests and deployment validation.

Actual recipient matrices, message schedules, escalation targets, and compatibility aliases belong in `market-intel-deploy`.
