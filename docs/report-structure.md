# Report Structure

Reports are assembled from validated facts, versioned owner artifacts, and deterministic rendering helpers.

## Public contract

Every report pipeline should make the following boundaries visible:

1. input facts and their source status;
2. validation and freshness results;
3. interpretation or scoring output;
4. rendered text, images, or dashboard payloads;
5. delivery receipt and idempotency scope.

The public repository documents layout and schema, not the identity of any recipient or the production message matrix.

## Offline behavior

When optional data or destinations are absent, reports should render a clearly marked degraded result or a dry-run artifact. Required owner artifacts fail closed when their contract or freshness checks do not pass.
